"""Evidence matching stage and deterministic requirement coverage."""

from __future__ import annotations

import json
from importlib import resources
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .profile import Profile, Work
from .provider import LLMProvider, LLMRequest
from .vacancy import VacancyAnalysis


class EvidenceMatchingError(ValueError):
    """Raised when evidence matching output violates its contract."""


class EvidenceMatch(BaseModel):
    """Evidence sources for one vacancy requirement."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    requirement_id: str = Field(pattern=r"^req-[0-9]{2,}$")
    source_paths: tuple[str, ...] = Field(min_length=1)
    strength: Literal["strong", "partial"]

    @field_validator("source_paths", mode="before")
    @classmethod
    def normalize_source_paths(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


class EvidenceMatching(BaseModel):
    """Versioned output of the evidence matching stage for one position."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal[2]
    matches: tuple[EvidenceMatch, ...]

    @field_validator("matches", mode="before")
    @classmethod
    def normalize_matches(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


class CoverageItem(BaseModel):
    """Coverage status for one vacancy requirement."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    requirement_id: str
    priority: Literal["must_have", "important", "nice_to_have", "context"]
    status: Literal["covered", "uncovered"]


class Coverage(BaseModel):
    """Deterministic coverage calculated from vacancy requirements and matches."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal[1]
    items: tuple[CoverageItem, ...]


def match_evidence(
    vacancy: VacancyAnalysis,
    work: Work,
    *,
    work_index: int,
    provider: LLMProvider,
) -> EvidenceMatching:
    """Find evidence sources for one work position through the provider."""
    if work_index < 0:
        raise EvidenceMatchingError("work_index must not be negative")

    response = provider.generate_json(
        LLMRequest(
            system_prompt=_system_prompt(),
            task_prompt=_task_prompt(),
            user_prompt=_user_prompt(vacancy, work, work_index),
        )
    )
    try:
        result = EvidenceMatching.model_validate(response.payload)
        valid_source_paths = {
            *(f"work[{work_index}].facts[{index}]" for index in range(len(work.facts))),
            *(f"work[{work_index}].skills[{index}]" for index in range(len(work.skills))),
        }
        _validate_matches(result, vacancy, valid_source_paths)
    except (ValidationError, EvidenceMatchingError) as error:
        if isinstance(error, EvidenceMatchingError):
            raise
        first = error.errors()[0]
        path = ".".join(str(part) for part in first["loc"]) or "matching"
        raise EvidenceMatchingError(f"Evidence matching field {path}: {first['msg']}") from error
    return result


def match_profile_evidence(vacancy: VacancyAnalysis, profile: Profile, *, provider: LLMProvider) -> EvidenceMatching:
    """Match requirements against structured, non-work profile sections."""
    sources = profile_evidence_sources(profile)
    if not sources:
        return EvidenceMatching(schema_version=2, matches=())
    response = provider.generate_json(
        LLMRequest(
            system_prompt=_system_prompt(),
            task_prompt=_profile_task_prompt(),
            user_prompt=json.dumps(
                {"vacancy": vacancy.model_dump(mode="json"), "sources": sources},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
        )
    )
    try:
        result = EvidenceMatching.model_validate(response.payload)
        _validate_matches(result, vacancy, set(sources))
    except (ValidationError, EvidenceMatchingError) as error:
        if isinstance(error, EvidenceMatchingError):
            raise
        first = error.errors()[0]
        path = ".".join(str(part) for part in first["loc"]) or "matching"
        raise EvidenceMatchingError(f"Evidence matching field {path}: {first['msg']}") from error
    return result


def calculate_coverage(vacancy: VacancyAnalysis, matchings: tuple[EvidenceMatching, ...]) -> Coverage:
    """Calculate candidate-requirement coverage without treating context as a gap."""
    covered = {match.requirement_id for matching in matchings for match in matching.matches}
    return Coverage(
        schema_version=1,
        items=tuple(
            CoverageItem(
                requirement_id=requirement.id,
                priority=requirement.priority,
                status="covered" if requirement.id in covered else "uncovered",
            )
            for requirement in vacancy.requirements
            if requirement.priority != "context"
        ),
    )


def _validate_matches(result: EvidenceMatching, vacancy: VacancyAnalysis, valid_source_paths: set[str]) -> None:
    requirement_ids = {requirement.id for requirement in vacancy.requirements}
    context_ids = {requirement.id for requirement in vacancy.requirements if requirement.priority == "context"}
    seen_requirements: set[str] = set()
    for match in result.matches:
        if match.requirement_id not in requirement_ids:
            raise EvidenceMatchingError(f"Unknown requirement ID: {match.requirement_id}")
        if match.requirement_id in context_ids:
            raise EvidenceMatchingError(f"Context is informational and cannot be matched: {match.requirement_id}")
        if match.requirement_id in seen_requirements:
            raise EvidenceMatchingError(f"Duplicate match for requirement: {match.requirement_id}")
        seen_requirements.add(match.requirement_id)
        unknown_paths = set(match.source_paths) - valid_source_paths
        if unknown_paths:
            paths = ", ".join(sorted(unknown_paths))
            label = "fact path(s)" if all(path.startswith("work[") for path in valid_source_paths) else "source path(s)"
            raise EvidenceMatchingError(f"Unknown {label}: {paths}")


def _system_prompt() -> str:
    return (
        resources.files("resume_generator.resources")
        .joinpath("prompts/evidence-matching/system.md")
        .read_text(encoding="utf-8")
    )


def _task_prompt() -> str:
    return (
        resources.files("resume_generator.resources")
        .joinpath("prompts/evidence-matching/task.md")
        .read_text(encoding="utf-8")
    )


def _profile_task_prompt() -> str:
    return (
        "Match the vacancy requirements against the supplied structured profile sources. "
        "Return schema_version 2 and use source_paths. A source is evidence only when "
        "its supplied text directly supports the requirement."
    )


def profile_evidence_sources(profile: Profile) -> dict[str, dict[str, str]]:
    """Build the addressable non-work evidence index."""
    sources: dict[str, dict[str, str]] = {}
    for index, item in enumerate(profile.languages):
        sources[f"languages[{index}]"] = {"path": f"languages[{index}]", "text": f"{item.language}: {item.level}"}
    for index, item in enumerate(profile.education):
        details = ", ".join(part for part in (item.study_type, item.area, item.institution) if part)
        dates = " - ".join(part for part in (item.start_date, item.end_date) if part)
        sources[f"education[{index}]"] = {
            "path": f"education[{index}]",
            "text": ", ".join(part for part in (details, dates) if part),
        }
    return sources


def _user_prompt(vacancy: VacancyAnalysis, work: Work, work_index: int) -> str:
    position = {
        "work_path": f"work[{work_index}]",
        "company": work.company,
        "position": work.position,
        "start_date": work.start_date,
        "end_date": work.end_date,
        "skills": [
            {"path": f"work[{work_index}].skills[{index}]", "text": skill} for index, skill in enumerate(work.skills)
        ],
        "facts": [
            {"path": f"work[{work_index}].facts[{index}]", "text": fact.text} for index, fact in enumerate(work.facts)
        ],
    }
    return json.dumps(
        {"vacancy": vacancy.model_dump(mode="json"), "position": position}, ensure_ascii=False, indent=2, sort_keys=True
    )
