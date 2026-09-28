"""Vacancy analysis stage and its versioned output contract."""

from __future__ import annotations

import json
from importlib import resources
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .issue import ResumeTask
from .provider import LLMProvider, LLMRequest


class VacancyAnalysisError(ValueError):
    """Raised when vacancy analysis output does not satisfy its contract."""


class VacancyRequirement(BaseModel):
    """One explicit requirement extracted from a vacancy."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    id: str = Field(pattern=r"^req-[0-9]{2,}$")
    text: str = Field(min_length=1)
    priority: Literal["must_have", "important", "nice_to_have", "context"]


class VacancyAnalysis(BaseModel):
    """Structured vacancy data produced by the analysis stage."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal[1]
    role: str = Field(min_length=1)
    requirements: tuple[VacancyRequirement, ...]
    responsibilities: tuple[str, ...]
    technologies: tuple[str, ...]
    domains: tuple[str, ...]
    signals: tuple[str, ...]

    @field_validator("requirements", "responsibilities", "technologies", "domains", "signals", mode="before")
    @classmethod
    def normalize_json_arrays(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def validate_requirement_ids(self) -> VacancyAnalysis:
        expected = [f"req-{index:02d}" for index in range(1, len(self.requirements) + 1)]
        actual = [requirement.id for requirement in self.requirements]
        if actual != expected:
            raise ValueError("requirements must use sequential IDs starting at req-01")
        return self


def analyze_vacancy(task: ResumeTask, provider: LLMProvider) -> VacancyAnalysis:
    """Analyze one vacancy through the configured structured-output provider."""
    request = LLMRequest(
        system_prompt=_system_prompt(),
        task_prompt=_task_prompt(),
        user_prompt=_user_prompt(task),
    )
    response = provider.generate_json(request)
    try:
        return VacancyAnalysis.model_validate(response.payload)
    except ValidationError as error:
        first = error.errors()[0]
        path = ".".join(str(part) for part in first["loc"]) or "analysis"
        raise VacancyAnalysisError(f"Vacancy analysis field {path}: {first['msg']}") from error


def _system_prompt() -> str:
    return (
        resources.files("resume_generator.resources")
        .joinpath("prompts/vacancy-analysis/system.md")
        .read_text(encoding="utf-8")
    )


def _task_prompt() -> str:
    return (
        resources.files("resume_generator.resources")
        .joinpath("prompts/vacancy-analysis/task.md")
        .read_text(encoding="utf-8")
    )


def _user_prompt(task: ResumeTask) -> str:
    payload = {
        "company": task.company,
        "position": task.position,
        "language": task.language,
        "job_description": task.job_description,
        "additional_instructions": task.additional_instructions,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
