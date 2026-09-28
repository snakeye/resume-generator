import pytest

from resume_generator.pipeline import PipelineError, RunContext, write_json_stage
from resume_generator.schemas import SchemaValidationError, validate_stage_artifact


def test_stage_artifact_schema_rejects_missing_required_field():
    with pytest.raises(SchemaValidationError, match="producer"):
        validate_stage_artifact({"schema_version": 1, "run_id": "run-1", "payload": {}})


def test_stage_artifact_schema_rejects_unknown_field():
    with pytest.raises(SchemaValidationError, match="unexpected"):
        validate_stage_artifact(
            {
                "schema_version": 1,
                "producer": "vacancy",
                "run_id": "run-1",
                "payload": {},
                "unexpected": True,
            }
        )


def test_invalid_stage_artifact_is_rejected_before_file_creation(tmp_path):
    context = RunContext(root=tmp_path, run_id="invalid/run")

    with pytest.raises(PipelineError, match="run_id"):
        write_json_stage(context, "10-vacancy", {}, producer="vacancy")

    assert not (tmp_path / "data/runs/invalid/run/stages/10-vacancy.json").exists()
