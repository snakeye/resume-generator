"""Deterministic relevant skills selection."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .terminology import TerminologyAnalysis


class SelectedSkill(BaseModel):
    """One profile-backed vacancy term selected for the skills section."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    category: Literal["technology", "competency"]
    group: str = Field(min_length=1)
    name: str = Field(min_length=1)
    canonical: str = Field(min_length=1)


class SkillsSelection(BaseModel):
    """Versioned output of deterministic skills selection."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal[2]
    skills: tuple[SelectedSkill, ...]


def select_skills(terminology: TerminologyAnalysis) -> SkillsSelection:
    """Select profile-backed vacancy terms in vacancy order."""
    seen: set[str] = set()
    selected_groups: set[str] = set()
    selected: list[SelectedSkill] = []
    for term in terminology.vacancy_terms:
        if not term.profile_match:
            continue
        category = "technology" if term.category == "technology" else "competency"
        if term.canonical in seen:
            continue
        seen.add(term.canonical)
        group = term.groups[0] if term.groups else ("Technology" if category == "technology" else "Core Competencies")
        if group not in selected_groups and len(selected_groups) >= 5:
            continue
        selected_groups.add(group)
        selected.append(SelectedSkill(category=category, group=group, name=term.source, canonical=term.canonical))
    return SkillsSelection(schema_version=2, skills=tuple(selected))
