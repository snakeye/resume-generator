"""Deterministic assembly of inspectable resume content."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .experience import experience_groups
from .headline import Headline
from .profile import Basics, Profile
from .skills import SkillsSelection
from .voice import AdaptedText, VoiceAdaptation


class ResumeAssemblyError(ValueError):
    """Raised when generated content cannot be assembled safely."""


class ResumeRole(BaseModel):
    """One role displayed inside a company experience block."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    work_path: str
    position: str = Field(min_length=1)
    start_date: str
    end_date: str | None = None
    bullets: tuple[AdaptedText, ...]
    tech_stack: tuple[str, ...]


class ResumeEarlierRole(BaseModel):
    """A source-backed role rendered inside the Earlier Experience block."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    work_path: str
    company: str = Field(min_length=1)
    location: str | None = None
    position: str = Field(min_length=1)
    start_date: str
    end_date: str | None = None
    bullets: tuple[AdaptedText, ...]
    tech_stack: tuple[str, ...]


class ResumeEarlierExperience(BaseModel):
    """One compact block backed by the grouped earlier work history."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    position: str = Field(min_length=1)
    start_date: str
    end_date: str
    bullets: tuple[AdaptedText, ...]
    tech_stack: tuple[str, ...]
    source_roles: tuple[ResumeEarlierRole, ...] = Field(min_length=1)


class ResumeCompany(BaseModel):
    """Company block containing one or more chronological roles."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    company: str = Field(min_length=1)
    location: str | None = None
    roles: tuple[ResumeRole, ...] = Field(min_length=1)


class ResumeEducation(BaseModel):
    """Education entry prepared for the rendering template."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    institution: str = Field(min_length=1)
    degree_line: str = ""
    start_date: str | None = None
    end_date: str | None = None
    details: tuple[str, ...] = ()


class ResumeLanguage(BaseModel):
    """Language and proficiency displayed in the resume."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    language: str = Field(min_length=1)
    level: str = Field(min_length=1)


class ResumeDocument(BaseModel):
    """Versioned assembled resume content before rendering."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal[3]
    basics: Basics
    headline: Headline
    summary: AdaptedText
    skills: SkillsSelection
    experience: tuple[ResumeCompany, ...]
    earlier_experience: ResumeEarlierExperience | None
    education: tuple[ResumeEducation, ...]
    languages: tuple[ResumeLanguage, ...]


_FACT_PATH_RE = re.compile(r"^work\[(?P<work>\d+)\]\.facts\[\d+\]$")


def assemble_resume(
    profile: Profile,
    headline: Headline,
    voice: VoiceAdaptation,
    skills: SkillsSelection,
) -> ResumeDocument:
    """Assemble generated sections with immutable profile fields unchanged."""
    bullets_by_work = _group_bullets(profile, voice)
    experience, earlier_experience = _assemble_experience(profile, bullets_by_work)
    return ResumeDocument(
        schema_version=3,
        basics=profile.basics,
        headline=headline,
        summary=voice.summary,
        skills=skills,
        experience=experience,
        earlier_experience=earlier_experience,
        education=tuple(
            ResumeEducation(
                institution=item.institution,
                degree_line=_degree_line(item.area, item.study_type),
                start_date=item.start_date,
                end_date=item.end_date,
                details=item.details,
            )
            for item in profile.education
        ),
        languages=tuple(ResumeLanguage(language=item.language, level=item.level) for item in profile.languages),
    )


def _assemble_experience(
    profile: Profile, bullets_by_work: list[list[AdaptedText]]
) -> tuple[tuple[ResumeCompany, ...], ResumeEarlierExperience | None]:
    companies: list[ResumeCompany] = []
    indexes: dict[tuple[str, str | None], int] = {}
    earlier_roles: list[ResumeEarlierRole] = []
    earlier_indexes = {index for group in experience_groups(profile) if group.earlier for index in group.work_indexes}
    for index, position in enumerate(profile.work):
        if index in earlier_indexes:
            earlier_roles.append(
                ResumeEarlierRole(
                    work_path=f"work[{index}]",
                    company=position.company,
                    location=position.location,
                    position=position.position,
                    start_date=position.start_date,
                    end_date=position.end_date,
                    bullets=tuple(bullets_by_work[index]),
                    tech_stack=tuple(position.skills),
                )
            )
            continue
        key = (position.company, position.location)
        role = ResumeRole(
            work_path=f"work[{index}]",
            position=position.position,
            start_date=position.start_date,
            end_date=position.end_date,
            bullets=tuple(bullets_by_work[index]),
            tech_stack=tuple(position.skills),
        )
        company_index = indexes.get(key)
        if company_index is None:
            indexes[key] = len(companies)
            companies.append(ResumeCompany(company=position.company, location=position.location, roles=(role,)))
            continue
        company = companies[company_index]
        companies[company_index] = company.model_copy(update={"roles": (*company.roles, role)})
    if not earlier_roles:
        return tuple(companies), None
    stack = tuple(dict.fromkeys(skill for role in earlier_roles for skill in role.tech_stack))
    return (
        tuple(companies),
        ResumeEarlierExperience(
            position="Software Engineer / Team Lead",
            start_date=min(role.start_date for role in earlier_roles),
            end_date=max(role.end_date or "Present" for role in earlier_roles),
            bullets=tuple(bullet for role in earlier_roles for bullet in role.bullets),
            tech_stack=stack,
            source_roles=tuple(earlier_roles),
        ),
    )


def _degree_line(area: str | None, study_type: str | None) -> str:
    if area and study_type:
        return f"{study_type} in {area}"
    return study_type or area or ""


def _group_bullets(profile: Profile, voice: VoiceAdaptation) -> list[list[AdaptedText]]:
    grouped = [[] for _ in profile.work]
    for bullet in voice.bullets:
        work_indexes = {_fact_work_index(path) for path in bullet.fact_paths}
        if len(work_indexes) != 1:
            raise ResumeAssemblyError("A bullet cannot combine facts from multiple work positions")
        work_index = work_indexes.pop()
        if work_index >= len(profile.work):
            raise ResumeAssemblyError(f"Bullet references unknown work position: work[{work_index}]")
        grouped[work_index].append(bullet)
    return grouped


def _fact_work_index(path: str) -> int:
    match = _FACT_PATH_RE.fullmatch(path)
    if match is None:
        raise ResumeAssemblyError(f"Invalid fact path: {path}")
    return int(match.group("work"))
