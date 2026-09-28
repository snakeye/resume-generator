"""Pydantic validation for versioned JSON contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class SchemaValidationError(ValueError):
    """Raised when a value does not satisfy an application schema."""


class StageArtifact(BaseModel):
    """Persisted envelope shared by all pipeline stages."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: int = Field(ge=1)
    producer: str = Field(min_length=1)
    run_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    payload: dict[str, Any]


def validate_stage_artifact(value: Mapping[str, Any]) -> StageArtifact:
    """Validate one persisted stage artifact against its versioned schema."""
    if not isinstance(value, Mapping):
        raise SchemaValidationError("Stage artifact is invalid: expected an object")
    try:
        return StageArtifact.model_validate(value)
    except ValidationError as error:
        first = error.errors()[0]
        path = ".".join(str(part) for part in first["loc"]) or "artifact"
        raise SchemaValidationError(f"Stage artifact is invalid: {path} {first['msg']}") from error
