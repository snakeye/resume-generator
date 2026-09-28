"""Fact selection stage with evidence-preserving validation."""

from __future__ import annotations

import json
import re
from importlib import resources
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .evidence import EvidenceMatching, profile_evidence_sources
from .experience import ExperienceGroup, experience_groups
from .profile import Profile
from .provider import LLMProvider, LLMRequest
from .vacancy import VacancyAnalysis

_FACT_PATH_RE = re.compile(r"^work\[(?P<work>[0-9]+)\]\.facts\[[0-9]+\]$")


class FactSelectionError(ValueError):
    """Raised when fact selection output is not supported by evidence."""


class SelectedFact(BaseModel):
    """One existing fact selected for the generated resume."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    fact_path: str = Field(pattern=r"^work\[[0-9]+\]\.facts\[[0-9]+\]$")
    covers: tuple[str, ...]

    @field_validator("covers", mode="before")
    @classmethod
    def normalize_covers(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


class FactSelectionDraft(BaseModel):
    """LLM output containing only the semantic fact selection."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal[3]
    selected: tuple[SelectedFact, ...]

    @field_validator("selected", mode="before")
    @classmethod
    def normalize_selected(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


class FactSelection(BaseModel):
    """Versioned output of the fact selection stage."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal[2]
    selected: tuple[SelectedFact, ...]
    uncovered: tuple[str, ...]

    @field_validator("selected", "uncovered", mode="before")
    @classmethod
    def normalize_arrays(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


def select_facts(
    vacancy: VacancyAnalysis,
    profile: Profile,
    matchings: tuple[EvidenceMatching, ...],
    provider: LLMProvider,
) -> FactSelection:
    """Select existing facts through the provider and validate their provenance."""
    response = provider.generate_json(
        LLMRequest(
            system_prompt=_system_prompt(),
            task_prompt=_task_prompt(),
            user_prompt=_user_prompt(vacancy, profile, matchings),
        )
    )
    try:
        draft = FactSelectionDraft.model_validate(response.payload)
        result = FactSelection(schema_version=2, selected=draft.selected, uncovered=())
        result = _supplement_unmatched_facts(result, profile, matchings)
        uncovered = _validate_selection(result, vacancy, profile, matchings)
        result = result.model_copy(update={"uncovered": uncovered})
    except (ValidationError, FactSelectionError) as error:
        if isinstance(error, FactSelectionError):
            raise
        first = error.errors()[0]
        path = ".".join(str(part) for part in first["loc"]) or "selection"
        raise FactSelectionError(f"Fact selection field {path}: {first['msg']}") from error
    return result


def _supplement_unmatched_facts(
    result: FactSelection,
    profile: Profile,
    matchings: tuple[EvidenceMatching, ...],
) -> FactSelection:
    """Fill an LLM omission with source facts that have no evidence match."""
    selected_paths = {fact.fact_path for fact in result.selected}
    matched_paths = {
        source_path
        for matching in matchings
        for match in matching.matches
        for source_path in match.source_paths
        if source_path.startswith("work[")
    }
    additions: list[SelectedFact] = []
    for group in experience_groups(profile):
        additions.extend(_supplement_group(result.selected, additions, profile, group, selected_paths, matched_paths))
    if not additions:
        return result
    return result.model_copy(update={"selected": (*result.selected, *additions)})


def _supplement_group(
    selected: tuple[SelectedFact, ...],
    additions: list[SelectedFact],
    profile: Profile,
    group: ExperienceGroup,
    selected_paths: set[str],
    matched_paths: set[str],
) -> list[SelectedFact]:
    required = min(
        profile.preferences.minimum_experience_bullets,
        sum(len(profile.work[index].facts) for index in group.work_indexes),
    )
    selected_count = sum(
        1 for fact in (*selected, *additions) if _fact_work_index(fact.fact_path) in group.work_indexes
    )
    if selected_count >= required:
        return []
    result: list[SelectedFact] = []
    for work_index in group.work_indexes:
        for fact_index in range(len(profile.work[work_index].facts)):
            fact_path = f"work[{work_index}].facts[{fact_index}]"
            if fact_path in selected_paths or fact_path in matched_paths:
                continue
            result.append(SelectedFact(fact_path=fact_path, covers=()))
            selected_paths.add(fact_path)
            selected_count += 1
            if selected_count >= required:
                return result
    return result


def _fact_work_index(path: str) -> int:
    match = _FACT_PATH_RE.fullmatch(path)
    return -1 if match is None else int(match.group("work"))


def _validate_selection(
    result: FactSelection,
    vacancy: VacancyAnalysis,
    profile: Profile,
    matchings: tuple[EvidenceMatching, ...],
) -> tuple[str, ...]:
    requirement_ids = {requirement.id for requirement in vacancy.requirements if requirement.priority != "context"}
    valid_fact_paths = {
        f"work[{work_index}].facts[{fact_index}]"
        for work_index, work in enumerate(profile.work)
        for fact_index in range(len(work.facts))
    }
    evidence_by_fact: dict[str, set[str]] = {}
    passthrough_requirements: set[str] = set()
    for matching in matchings:
        for match in matching.matches:
            for source_path in match.source_paths:
                if _FACT_PATH_RE.fullmatch(source_path):
                    evidence_by_fact.setdefault(source_path, set()).add(match.requirement_id)
                else:
                    passthrough_requirements.add(match.requirement_id)

    covered_requirements = _validate_selected_facts(
        result.selected, requirement_ids, valid_fact_paths, evidence_by_fact
    )
    _validate_group_minimums(result.selected, profile)
    covered_requirements.update(passthrough_requirements)
    return tuple(
        requirement.id
        for requirement in vacancy.requirements
        if requirement.priority != "context" and requirement.id not in covered_requirements
    )


def _validate_selected_facts(
    selected_facts: tuple[SelectedFact, ...],
    requirement_ids: set[str],
    valid_fact_paths: set[str],
    evidence_by_fact: dict[str, set[str]],
) -> set[str]:
    selected_paths: set[str] = set()
    covered_requirements: set[str] = set()
    for selected in selected_facts:
        if selected.fact_path in selected_paths:
            raise FactSelectionError(f"Duplicate selected fact: {selected.fact_path}")
        selected_paths.add(selected.fact_path)
        _validate_selected_fact(selected, requirement_ids, valid_fact_paths, evidence_by_fact)
        covered_requirements.update(selected.covers)
    return covered_requirements


def _validate_selected_fact(
    selected: SelectedFact,
    requirement_ids: set[str],
    valid_fact_paths: set[str],
    evidence_by_fact: dict[str, set[str]],
) -> None:
    if selected.fact_path not in valid_fact_paths:
        raise FactSelectionError(f"Unknown fact path: {selected.fact_path}")
    supported_requirements = evidence_by_fact.get(selected.fact_path, set())
    if not selected.covers:
        if supported_requirements:
            raise FactSelectionError(f"Matched fact must cover at least one requirement: {selected.fact_path}")
        return
    if not supported_requirements:
        raise FactSelectionError(f"Selected fact covers a requirement without an evidence match: {selected.fact_path}")
    unknown_requirements = set(selected.covers) - requirement_ids
    if unknown_requirements:
        raise FactSelectionError(f"Unknown requirement ID(s): {', '.join(sorted(unknown_requirements))}")
    unsupported_requirements = set(selected.covers) - supported_requirements
    if unsupported_requirements:
        names = ", ".join(sorted(unsupported_requirements))
        raise FactSelectionError(f"Fact {selected.fact_path} does not support requirement(s): {names}")


def _validate_group_minimums(selected_facts: tuple[SelectedFact, ...], profile: Profile) -> None:
    selected_by_work = [0] * len(profile.work)
    for selected in selected_facts:
        match = _FACT_PATH_RE.fullmatch(selected.fact_path)
        if match is not None:
            selected_by_work[int(match.group("work"))] += 1
    for group in experience_groups(profile):
        available = sum(len(profile.work[index].facts) for index in group.work_indexes)
        selected = sum(selected_by_work[index] for index in group.work_indexes)
        required = min(profile.preferences.minimum_experience_bullets, available)
        if selected < required:
            label = (
                f"work[{group.work_indexes[0]}]"
                if len(group.work_indexes) == 1
                else f"experience group {group.work_indexes}"
            )
            raise FactSelectionError(f"{label} requires at least {required} selected fact(s); got {selected}")


def _system_prompt() -> str:
    return (
        resources.files("resume_generator.resources")
        .joinpath("prompts/fact-selection/system.md")
        .read_text(encoding="utf-8")
    )


def _task_prompt() -> str:
    return (
        resources.files("resume_generator.resources")
        .joinpath("prompts/fact-selection/task.md")
        .read_text(encoding="utf-8")
    )


def _user_prompt(
    vacancy: VacancyAnalysis,
    profile: Profile,
    matchings: tuple[EvidenceMatching, ...],
) -> str:
    positions = []
    for work_index, work in enumerate(profile.work):
        positions.append(
            {
                "work_path": f"work[{work_index}]",
                "company": work.company,
                "position": work.position,
                "start_date": work.start_date,
                "end_date": work.end_date,
                "facts": [
                    {"path": f"work[{work_index}].facts[{fact_index}]", "text": fact.text}
                    for fact_index, fact in enumerate(work.facts)
                ],
            }
        )
    fact_matching_groups = []
    passthrough_matching_groups = []
    for matching in matchings:
        fact_matches = []
        passthrough_matches = []
        for match in matching.matches:
            fact_paths = tuple(path for path in match.source_paths if _FACT_PATH_RE.fullmatch(path))
            if fact_paths:
                fact_matches.append(
                    {
                        "requirement_id": match.requirement_id,
                        "source_paths": list(fact_paths),
                        "strength": match.strength,
                    }
                )
            if len(fact_paths) != len(match.source_paths):
                passthrough_matches.append(
                    {
                        "requirement_id": match.requirement_id,
                        "source_paths": [path for path in match.source_paths if path not in fact_paths],
                        "strength": match.strength,
                    }
                )
        if fact_matches:
            fact_matching_groups.append({"schema_version": matching.schema_version, "matches": fact_matches})
        if passthrough_matches:
            passthrough_matching_groups.append(
                {"schema_version": matching.schema_version, "matches": passthrough_matches}
            )
    return json.dumps(
        {
            "vacancy": vacancy.model_dump(mode="json"),
            "evidence_matches": fact_matching_groups,
            "passthrough_matches": passthrough_matching_groups,
            "minimum_facts_per_position": profile.preferences.minimum_experience_bullets,
            "experience_groups": [
                {"work_indexes": group.work_indexes, "earlier": group.earlier} for group in experience_groups(profile)
            ],
            "passthrough_sources": list(profile_evidence_sources(profile).values()),
            "positions": positions,
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
