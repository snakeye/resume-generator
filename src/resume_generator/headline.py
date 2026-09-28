"""Headline generation with explicit selected-fact provenance."""

from __future__ import annotations

import json
from importlib import resources
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .profile import Profile
from .provider import LLMProvider, LLMRequest
from .selection import FactSelection
from .vacancy import VacancyAnalysis


class HeadlineGenerationError(ValueError):
    """Raised when headline output is not supported by selected facts."""


class Headline(BaseModel):
    """Versioned output of the headline generation stage."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal[1]
    text: str = Field(min_length=1)
    fact_paths: tuple[str, ...] = Field(min_length=1)

    @field_validator("fact_paths", mode="before")
    @classmethod
    def normalize_fact_paths(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


def generate_headline(
    vacancy: VacancyAnalysis,
    profile: Profile,
    selection: FactSelection,
    provider: LLMProvider,
) -> Headline:
    """Generate one vacancy-specific headline from selected profile facts."""
    response = provider.generate_json(
        LLMRequest(
            system_prompt=_system_prompt(),
            task_prompt=_task_prompt(),
            user_prompt=_user_prompt(vacancy, profile, selection),
        )
    )
    try:
        result = Headline.model_validate(response.payload)
        _validate_provenance(result, profile, selection)
    except (ValidationError, HeadlineGenerationError) as error:
        if isinstance(error, HeadlineGenerationError):
            raise
        first = error.errors()[0]
        path = ".".join(str(part) for part in first["loc"]) or "headline"
        raise HeadlineGenerationError(f"Headline field {path}: {first['msg']}") from error
    return result


def _validate_provenance(result: Headline, profile: Profile, selection: FactSelection) -> None:
    selected_paths = {fact.fact_path for fact in selection.selected}
    valid_paths = {
        f"work[{work_index}].facts[{fact_index}]"
        for work_index, work in enumerate(profile.work)
        for fact_index in range(len(work.facts))
    }
    if len(result.fact_paths) != len(set(result.fact_paths)):
        raise HeadlineGenerationError("fact_paths must not contain duplicates")
    unknown_paths = set(result.fact_paths) - valid_paths
    if unknown_paths:
        raise HeadlineGenerationError(f"Unknown fact path(s): {', '.join(sorted(unknown_paths))}")
    unselected_paths = set(result.fact_paths) - selected_paths
    if unselected_paths:
        raise HeadlineGenerationError(
            f"Headline references unselected fact path(s): {', '.join(sorted(unselected_paths))}"
        )


def _system_prompt() -> str:
    return (
        resources.files("resume_generator.resources")
        .joinpath("prompts/headline-generation/system.md")
        .read_text(encoding="utf-8")
    )


def _task_prompt() -> str:
    return (
        resources.files("resume_generator.resources")
        .joinpath("prompts/headline-generation/task.md")
        .read_text(encoding="utf-8")
    )


def _user_prompt(vacancy: VacancyAnalysis, profile: Profile, selection: FactSelection) -> str:
    selected_paths = {fact.fact_path for fact in selection.selected}
    positions = []
    for work_index, work in enumerate(profile.work):
        facts = [
            {
                "path": f"work[{work_index}].facts[{fact_index}]",
                "text": fact.text,
            }
            for fact_index, fact in enumerate(work.facts)
            if f"work[{work_index}].facts[{fact_index}]" in selected_paths
        ]
        if facts:
            positions.append(
                {
                    "work_path": f"work[{work_index}]",
                    "company": work.company,
                    "position": work.position,
                    "facts": facts,
                }
            )
    return json.dumps(
        {
            "role": vacancy.role,
            "selected": selection.model_dump(mode="json"),
            "positions": positions,
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
