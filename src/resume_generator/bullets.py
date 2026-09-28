"""Bullet generation with provenance for every generated bullet."""

from __future__ import annotations

import json
import re
from importlib import resources
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .experience import experience_groups
from .profile import Profile
from .provider import LLMProvider, LLMRequest
from .selection import FactSelection
from .terminology import TerminologyAnalysis
from .vacancy import VacancyAnalysis

_FACT_PATH_RE = re.compile(r"^work\[(?P<work>[0-9]+)\]\.facts\[[0-9]+\]$")


class BulletGenerationError(ValueError):
    """Raised when generated bullets violate their provenance contract."""


class ResumeBullet(BaseModel):
    """One generated bullet and the facts that support it."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    text: str = Field(min_length=1)
    fact_paths: tuple[str, ...] = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("fact_paths", mode="before")
    @classmethod
    def normalize_fact_paths(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


class BulletGeneration(BaseModel):
    """Versioned output of the bullet generation stage."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal[2]
    bullets: tuple[ResumeBullet, ...]

    @field_validator("bullets", mode="before")
    @classmethod
    def normalize_bullets(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


def generate_bullets(
    vacancy: VacancyAnalysis,
    terminology: TerminologyAnalysis,
    profile: Profile,
    selection: FactSelection,
    provider: LLMProvider,
) -> BulletGeneration:
    """Generate readable bullets from selected facts without changing evidence."""
    response = provider.generate_json(
        LLMRequest(
            system_prompt=_system_prompt(),
            task_prompt=_task_prompt(),
            user_prompt=_user_prompt(vacancy, terminology, profile, selection),
        )
    )
    try:
        result = BulletGeneration.model_validate(response.payload)
        _validate_provenance(result, profile, selection)
    except (ValidationError, BulletGenerationError) as error:
        if isinstance(error, BulletGenerationError):
            raise
        first = error.errors()[0]
        path = ".".join(str(part) for part in first["loc"]) or "bullets"
        raise BulletGenerationError(f"Bullet generation field {path}: {first['msg']}") from error
    return result


def _validate_provenance(result: BulletGeneration, profile: Profile, selection: FactSelection) -> None:
    selected_paths = {fact.fact_path for fact in selection.selected}
    valid_paths = {
        f"work[{work_index}].facts[{fact_index}]"
        for work_index, work in enumerate(profile.work)
        for fact_index in range(len(work.facts))
    }
    used_paths: set[str] = set()
    bullets_by_work = [0] * len(profile.work)
    for bullet in result.bullets:
        if len(bullet.fact_paths) != len(set(bullet.fact_paths)):
            raise BulletGenerationError("bullet fact_paths must not contain duplicates")
        unknown_paths = set(bullet.fact_paths) - valid_paths
        if unknown_paths:
            raise BulletGenerationError(f"Unknown fact path(s): {', '.join(sorted(unknown_paths))}")
        unselected_paths = set(bullet.fact_paths) - selected_paths
        if unselected_paths:
            raise BulletGenerationError(
                f"Bullet references unselected fact path(s): {', '.join(sorted(unselected_paths))}"
            )
        bullets_by_work[_bullet_work_index(bullet.fact_paths)] += 1
        used_paths.update(bullet.fact_paths)
    unused_paths = selected_paths - used_paths
    if unused_paths:
        raise BulletGenerationError(f"Selected fact path(s) missing from bullets: {', '.join(sorted(unused_paths))}")
    _validate_position_minimums(bullets_by_work, profile)


def _bullet_work_index(fact_paths: tuple[str, ...]) -> int:
    work_indexes = {
        int(match.group("work")) for path in fact_paths if (match := _FACT_PATH_RE.fullmatch(path)) is not None
    }
    if len(work_indexes) != 1:
        raise BulletGenerationError("A bullet cannot combine facts from multiple work positions")
    return work_indexes.pop()


def _validate_position_minimums(bullets_by_work: list[int], profile: Profile) -> None:
    for group in experience_groups(profile):
        available = sum(len(profile.work[index].facts) for index in group.work_indexes)
        actual = sum(bullets_by_work[index] for index in group.work_indexes)
        required = min(profile.preferences.minimum_experience_bullets, available)
        if actual < required:
            label = (
                f"work[{group.work_indexes[0]}]"
                if len(group.work_indexes) == 1
                else f"experience group {group.work_indexes}"
            )
            raise BulletGenerationError(f"{label} requires at least {required} bullet(s); got {actual}")


def _system_prompt() -> str:
    return (
        resources.files("resume_generator.resources")
        .joinpath("prompts/bullet-generation/system.md")
        .read_text(encoding="utf-8")
    )


def _task_prompt() -> str:
    return (
        resources.files("resume_generator.resources")
        .joinpath("prompts/bullet-generation/task.md")
        .read_text(encoding="utf-8")
    )


def _user_prompt(
    vacancy: VacancyAnalysis,
    terminology: TerminologyAnalysis,
    profile: Profile,
    selection: FactSelection,
) -> str:
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
    requirement_ids = {requirement_id for selected in selection.selected for requirement_id in selected.covers}
    requirements = [
        requirement.model_dump(mode="json") for requirement in vacancy.requirements if requirement.id in requirement_ids
    ]
    return json.dumps(
        {
            "requirements": requirements,
            "minimum_bullets_per_position": profile.preferences.minimum_experience_bullets,
            "experience_groups": [
                {"work_indexes": group.work_indexes, "earlier": group.earlier} for group in experience_groups(profile)
            ],
            "terminology": terminology.model_dump(mode="json"),
            "voice": profile.voice.model_dump(mode="json"),
            "selected": selection.model_dump(mode="json"),
            "positions": positions,
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
