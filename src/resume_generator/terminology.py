"""Deterministic canonical terminology normalization."""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .profile import Profile
from .vacancy import VacancyAnalysis


class TerminologyError(ValueError):
    """Raised when the profile vocabulary cannot be normalized safely."""


class NormalizedVacancyTerm(BaseModel):
    """One vacancy vocabulary term with its canonical representation."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    category: Literal["technology", "domain", "signal"]
    source: str = Field(min_length=1)
    canonical: str = Field(min_length=1)
    profile_match: bool
    groups: tuple[str, ...] = ()


class TerminologyAnalysis(BaseModel):
    """Versioned output of terminology normalization."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal[1]
    profile_terms: tuple[str, ...]
    vacancy_terms: tuple[NormalizedVacancyTerm, ...]


def normalize_terminology(profile: Profile, vacancy: VacancyAnalysis) -> TerminologyAnalysis:
    """Normalize profile and analyzed vacancy vocabulary without using an LLM."""
    canonical_by_variant = _build_vocabulary(profile.aliases)
    profile_terms = _profile_terms(profile, canonical_by_variant)
    profile_term_set = set(profile_terms)
    vacancy_terms = _vacancy_terms(profile, vacancy, canonical_by_variant, profile_term_set)
    return TerminologyAnalysis(
        schema_version=1,
        profile_terms=tuple(profile_terms),
        vacancy_terms=tuple(vacancy_terms),
    )


def _build_vocabulary(aliases: dict[str, tuple[str, ...]]) -> dict[str, str]:
    variants: dict[str, str] = {}
    for canonical, values in aliases.items():
        canonical_key = _term_key(canonical)
        if not canonical_key:
            raise TerminologyError("Alias canonical term must not be empty.")
        _add_variant(variants, canonical_key, canonical_key)
        for value in values:
            variant = _term_key(value)
            if not variant:
                raise TerminologyError(f"Alias for '{canonical}' must not be empty.")
            _add_variant(variants, variant, canonical_key)
    return variants


def _add_variant(variants: dict[str, str], variant: str, canonical: str) -> None:
    existing = variants.get(variant)
    if existing is not None and existing != canonical:
        raise TerminologyError(f"Alias '{variant}' maps to multiple canonical terms.")
    variants[variant] = canonical


def _profile_terms(profile: Profile, vocabulary: dict[str, str]) -> list[str]:
    terms: list[str] = []
    for skill in [*profile.skills, *(skill for work in profile.work for skill in work.skills)]:
        canonical = vocabulary.get(_term_key(skill), _term_key(skill))
        if canonical not in terms:
            terms.append(canonical)
    return terms


def _vacancy_terms(
    profile: Profile,
    vacancy: VacancyAnalysis,
    vocabulary: dict[str, str],
    profile_terms: set[str],
) -> list[NormalizedVacancyTerm]:
    groups_by_term: dict[str, list[str]] = {}
    for group in profile.skill_groups:
        for keyword in group.keywords:
            canonical = vocabulary.get(_term_key(keyword), _term_key(keyword))
            groups_by_term.setdefault(canonical, []).append(group.name)
    terms: list[NormalizedVacancyTerm] = []
    for category, values in (
        ("technology", vacancy.technologies),
        ("domain", vacancy.domains),
        ("signal", vacancy.signals),
    ):
        seen: set[tuple[str, str]] = set()
        for source in values:
            source_key = _term_key(source)
            canonical = vocabulary.get(source_key, source_key)
            identity = (category, canonical)
            if identity in seen:
                continue
            seen.add(identity)
            terms.append(
                NormalizedVacancyTerm(
                    category=category,
                    source=source,
                    canonical=canonical,
                    profile_match=canonical in profile_terms,
                    groups=tuple(groups_by_term.get(canonical, ())),
                )
            )
    return terms


def _term_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    return re.sub(r"\s+", " ", normalized)
