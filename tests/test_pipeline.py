import json
import re
from datetime import datetime

import pytest

from resume_generator.pipeline import (
    PIPELINE_STAGE_NAMES,
    PipelineError,
    ResumeRequest,
    create_run,
    run_pipeline,
    write_json_stage,
    write_text,
)


def test_create_run_builds_inspectable_directory(tmp_path):
    context = create_run(tmp_path, "run-1")

    assert context.run_dir == tmp_path / "data/runs" / context.run_date / "run-1"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", context.run_date)
    assert context.input_dir.is_dir()
    assert context.stages_dir.is_dir()
    assert context.debug_dir.is_dir()
    metadata = json.loads((context.run_dir / "run-metadata.json").read_text(encoding="utf-8"))
    assert metadata["schema_version"] == 1
    assert metadata["run_id"] == "run-1"
    assert metadata["run_date"] == context.run_date
    datetime.fromisoformat(metadata["created_at"])


def test_existing_run_id_is_not_overwritten(tmp_path):
    create_run(tmp_path, "run-1")

    with pytest.raises(PipelineError, match="Run already exists"):
        create_run(tmp_path, "run-1")


def test_stage_json_contains_version_and_run_provenance(tmp_path):
    context = create_run(tmp_path, "run-1")

    path = write_json_stage(context, "10-vacancy", {"role": "Engineer"}, producer="vacancy")

    assert path == context.stages_dir / "10-vacancy.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "payload": {"role": "Engineer"},
        "producer": "vacancy",
        "run_id": "run-1",
        "schema_version": 1,
    }


def test_text_artifact_is_written_atomically(tmp_path):
    context = create_run(tmp_path, "run-1")

    path = write_text(context, "input/vacancy.txt", "A vacancy\n")

    assert path.read_text(encoding="utf-8") == "A vacancy\n"
    assert list(context.run_dir.rglob("*.tmp")) == []


def test_artifact_path_cannot_escape_run_directory(tmp_path):
    context = create_run(tmp_path, "run-1")

    with pytest.raises(PipelineError, match="stay inside"):
        write_text(context, "../outside.txt", "secret")

    assert not (context.run_dir.parent / "outside.txt").exists()


def test_pipeline_runs_stages_in_documented_order(tmp_path):
    calls = []
    stages = {
        name: lambda request, context, name=name: calls.append(name) or {"stage": name} for name in PIPELINE_STAGE_NAMES
    }

    result = run_pipeline(
        ResumeRequest(
            company="Example",
            position="Engineer",
            language="English",
            job_description="Build reliable systems",
        ),
        root=tmp_path,
        run_id="run-1",
        stages=stages,
    )

    assert result.success is True
    assert calls == list(PIPELINE_STAGE_NAMES)


def test_pipeline_reports_stage_lifecycle(tmp_path):
    events = []
    stages = {name: lambda request, context, name=name: {"stage": name} for name in PIPELINE_STAGE_NAMES}

    result = run_pipeline(
        ResumeRequest(company="Example", position="Engineer", language="English", job_description="Build systems"),
        root=tmp_path,
        run_id="run-1",
        stages=stages,
        on_stage=lambda status, name, payload, elapsed: events.append((status, name, payload is not None)),
    )

    assert result.success is True
    assert events == [
        event for name in PIPELINE_STAGE_NAMES for event in (("started", name, False), ("completed", name, True))
    ]


def test_pipeline_reports_failed_stage(tmp_path):
    events = []

    def fail(request, context):
        raise RuntimeError("provider unavailable")

    stages = {name: fail if name == "20-vacancy" else lambda request, context: {} for name in PIPELINE_STAGE_NAMES}
    result = run_pipeline(
        ResumeRequest(company="Example", position="Engineer", language="English", job_description="Build systems"),
        root=tmp_path,
        run_id="run-1",
        stages=stages,
        on_stage=lambda status, name, payload, elapsed: events.append((status, name)),
    )

    assert result.success is False
    assert events[-1] == ("failed", "20-vacancy")


def test_pipeline_stops_after_failed_stage(tmp_path):
    calls = []

    def failing_stage(request, context):
        calls.append("20-vacancy")
        raise RuntimeError("provider unavailable")

    stages = {
        name: failing_stage if name == "20-vacancy" else lambda request, context, name=name: calls.append(name) or {}
        for name in PIPELINE_STAGE_NAMES
    }

    result = run_pipeline(
        ResumeRequest(
            company="Example",
            position="Engineer",
            language="English",
            job_description="Build reliable systems",
        ),
        root=tmp_path,
        run_id="run-1",
        stages=stages,
    )

    assert result.success is False
    assert result.error == "provider unavailable"
    assert calls == ["10-input", "20-vacancy"]
    assert not (result.output_directory / "stages/20-vacancy.json").exists()


def test_pipeline_metadata_records_input_and_completed_stages(tmp_path):
    stages = {name: lambda request, context: {} for name in PIPELINE_STAGE_NAMES}

    result = run_pipeline(
        ResumeRequest(
            company="Example",
            position="Engineer",
            language="English",
            job_description="Build reliable systems",
        ),
        root=tmp_path,
        run_id="run-1",
        stages=stages,
    )

    metadata = json.loads((result.output_directory / "run-metadata.json").read_text(encoding="utf-8"))
    assert len(metadata["input_sha256"]) == 64
    assert metadata["completed_stages"] == list(PIPELINE_STAGE_NAMES)
    assert "job_description" not in json.dumps(metadata)
