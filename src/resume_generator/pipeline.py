"""Local run context and atomic pipeline artifact storage."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .schemas import SchemaValidationError, validate_stage_artifact


class PipelineError(RuntimeError):
    """Raised when a pipeline run cannot be created or persisted safely."""


_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

PIPELINE_STAGE_NAMES = (
    "10-input",
    "20-vacancy",
    "30-terminology",
    "40-evidence",
    "50-selection",
    "60-writing",
    "70-skills",
    "80-voice",
    "90-assembly",
    "100-validation",
    "110-rendering",
    "120-pdf-validation",
)

StageProgress = Callable[[str, str, Mapping[str, Any] | None, float | None], None]


class RunContext(BaseModel):
    """Paths belonging to one immutable local pipeline run."""

    model_config = ConfigDict(frozen=True)

    root: Path
    run_id: str
    run_date: str | None = None

    @property
    def run_dir(self) -> Path:
        runs_dir = self.root / "data" / "runs"
        return runs_dir / self.run_date / self.run_id if self.run_date else runs_dir / self.run_id

    @property
    def input_dir(self) -> Path:
        return self.run_dir / "input"

    @property
    def stages_dir(self) -> Path:
        return self.run_dir / "stages"

    @property
    def debug_dir(self) -> Path:
        return self.run_dir / "debug"


class ResumeRequest(BaseModel):
    """Input owned by the domain pipeline, not by GitHub-specific code."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    company: str = Field(min_length=1)
    position: str = Field(min_length=1)
    language: str = Field(min_length=1)
    job_description: str = Field(min_length=1)
    additional_instructions: str | None = None


class PipelineResult(BaseModel):
    """Inspectable outcome of one pipeline run."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    success: bool
    output_directory: Path
    error: str | None = None


def create_run(root: Path, run_id: str) -> RunContext:
    """Create an empty run directory and its inspectable subdirectories."""
    if not _RUN_ID_RE.fullmatch(run_id):
        raise PipelineError("run_id must contain only letters, numbers, '.', '_' or '-'.")

    run_date = datetime.now(UTC).date().isoformat()
    context = RunContext(root=root, run_id=run_id, run_date=run_date)
    try:
        context.run_dir.mkdir(parents=True, exist_ok=False)
        context.input_dir.mkdir()
        context.stages_dir.mkdir()
        context.debug_dir.mkdir()
    except FileExistsError as error:
        raise PipelineError(f"Run already exists: {run_id}. Use a new run_id for a retry.") from error
    except OSError as error:
        raise PipelineError(f"Cannot create run directory {context.run_dir}: {error}") from error

    metadata = {
        "schema_version": 1,
        "run_id": run_id,
        "run_date": run_date,
        "created_at": datetime.now(UTC).isoformat(),
        "completed_stages": [],
        "input_sha256": None,
        "git_commit": _git_commit(root),
    }
    try:
        _atomic_write(context.run_dir / "run-metadata.json", _json_text(metadata))
    except OSError as error:
        raise PipelineError(f"Cannot write run metadata: {error}") from error
    return context


def run_pipeline(
    request: ResumeRequest,
    *,
    root: Path,
    run_id: str,
    stages: Mapping[str, Any],
    on_run_created: Any | None = None,
    on_stage: StageProgress | None = None,
) -> PipelineResult:
    """Run supplied stages in the documented order and persist each result."""
    context = create_run(root, run_id)
    try:
        if on_run_created is not None:
            on_run_created(context)
        _validate_stage_set(stages)
        input_hash = _write_input(context, request)
        completed_stages: list[str] = []
        _update_metadata(context, input_hash=input_hash, completed_stages=completed_stages)

        for stage_name in PIPELINE_STAGE_NAMES:
            started_at = _monotonic()
            _notify_stage(on_stage, "started", stage_name, None, None)
            try:
                payload = stages[stage_name](request, context)
                write_json_stage(context, stage_name, payload, producer=stage_name)
            except Exception:
                _notify_stage(on_stage, "failed", stage_name, None, _monotonic() - started_at)
                raise
            completed_stages.append(stage_name)
            _update_metadata(context, input_hash=input_hash, completed_stages=completed_stages)
            _notify_stage(on_stage, "completed", stage_name, payload, _monotonic() - started_at)
    except Exception as error:  # noqa: BLE001 - convert stage failures to the public result contract
        return PipelineResult(success=False, output_directory=context.run_dir, error=str(error))
    return PipelineResult(success=True, output_directory=context.run_dir)


def write_text(context: RunContext, relative_path: str, content: str) -> Path:
    """Atomically write UTF-8 text below one run directory."""
    if not isinstance(content, str):
        raise PipelineError("Text artifact content must be a string.")
    path = _safe_path(context, relative_path)
    try:
        _atomic_write(path, content)
    except OSError as error:
        raise PipelineError(f"Cannot write artifact {relative_path}: {error}") from error
    return path


def write_json_stage(
    context: RunContext,
    stage_name: str,
    payload: Mapping[str, Any],
    *,
    producer: str,
    schema_version: int = 1,
) -> Path:
    """Write one versioned, inspectable stage payload atomically."""
    if not _RUN_ID_RE.fullmatch(stage_name):
        raise PipelineError("stage_name must contain only letters, numbers, '.', '_' or '-'.")
    artifact = {
        "schema_version": schema_version,
        "producer": producer,
        "run_id": context.run_id,
        "payload": payload,
    }
    try:
        validated = validate_stage_artifact(artifact)
    except SchemaValidationError as error:
        raise PipelineError(str(error)) from error
    return write_text(context, f"stages/{stage_name}.json", _json_text(validated.model_dump()))


def _safe_path(context: RunContext, relative_path: str) -> Path:
    candidate = Path(relative_path)
    if candidate.is_absolute() or not relative_path or ".." in candidate.parts:
        raise PipelineError("Artifact path must be relative and stay inside the run directory.")
    path = context.run_dir / candidate
    if path.parent != context.run_dir and not path.parent.is_relative_to(context.run_dir):
        raise PipelineError("Artifact path must stay inside the run directory.")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _json_text(value: Mapping[str, Any]) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    except (TypeError, ValueError) as error:
        raise PipelineError(f"Artifact is not JSON serializable: {error}") from error


def _validate_stage_set(stages: Mapping[str, Any]) -> None:
    missing = [name for name in PIPELINE_STAGE_NAMES if name not in stages]
    if missing:
        raise PipelineError(f"Missing pipeline stages: {', '.join(missing)}")
    non_callable = [name for name in PIPELINE_STAGE_NAMES if not callable(stages[name])]
    if non_callable:
        raise PipelineError(f"Pipeline stages must be callable: {', '.join(non_callable)}")


def _write_input(context: RunContext, request: ResumeRequest) -> str:
    input_data = {
        "company": request.company,
        "position": request.position,
        "language": request.language,
        "job_description": request.job_description,
        "additional_instructions": request.additional_instructions,
    }
    serialized = _json_text(input_data)
    write_text(context, "input/request.json", serialized)
    return _sha256(serialized)


def _update_metadata(context: RunContext, *, input_hash: str, completed_stages: list[str]) -> None:
    metadata = {
        "schema_version": 1,
        "run_id": context.run_id,
        "created_at": json.loads((context.run_dir / "run-metadata.json").read_text(encoding="utf-8"))["created_at"],
        "completed_stages": completed_stages,
        "input_sha256": input_hash,
        "git_commit": _git_commit(context.root),
    }
    _atomic_write(context.run_dir / "run-metadata.json", _json_text(metadata))


def _sha256(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _monotonic() -> float:
    import time

    return time.monotonic()


def _notify_stage(
    on_stage: StageProgress | None,
    status: str,
    stage_name: str,
    payload: Mapping[str, Any] | None,
    elapsed: float | None,
) -> None:
    if on_stage is not None:
        on_stage(status, stage_name, payload, elapsed)


def _git_commit(root: Path) -> str | None:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=False, capture_output=True, text=True)
    except OSError:
        return None
    commit = result.stdout.strip()
    return commit if result.returncode == 0 and commit else None


def _atomic_write(path: Path, content: str) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
