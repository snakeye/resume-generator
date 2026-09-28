"""Deterministic resume validation that never rewrites generated content."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .assembly import ResumeDocument, ResumeEarlierRole, ResumeRole
from .profile import Profile
from .vacancy import VacancyAnalysis


class ValidationIssue(BaseModel):
    """One accepted, warned, or rejected validation result."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    severity: Literal["warning", "error"]
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    path: str | None = None


class ValidationReport(BaseModel):
    """Versioned validation output suitable for an inspectable artifact."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal[1]
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def valid(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)


_FACT_PATH_RE = re.compile(r"^work\[(?P<work>\d+)\]\.facts\[(?P<fact>\d+)\]$")
_NUMBER_RE = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)?%?(?![A-Za-z])")


def validate_resume(
    profile: Profile,
    resume: ResumeDocument,
    *,
    vacancy: VacancyAnalysis | None = None,
    covered_requirements: frozenset[str] = frozenset(),
) -> ValidationReport:
    """Inspect a resume against its profile and optional vacancy coverage."""
    issues: list[ValidationIssue] = []
    issues.extend(_validate_immutable_fields(profile, resume))
    issues.extend(_validate_generated_text(profile, resume))
    issues.extend(_validate_text_quality(profile, resume))
    if vacancy is not None:
        issues.extend(_validate_coverage(vacancy, covered_requirements))
    return ValidationReport(schema_version=1, issues=tuple(issues))


def _validate_immutable_fields(profile: Profile, resume: ResumeDocument) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if resume.basics != profile.basics:
        issues.append(_error("immutable.basics", "Contact information differs from the profile.", "basics"))
    rendered_work = tuple(_rendered_work(resume))
    if len(rendered_work) != len(profile.work):
        return issues + [_error("immutable.work_count", "Work history count differs from the profile.", "experience")]
    seen_paths: set[str] = set()
    for company, role in rendered_work:
        issues.extend(_validate_work_entry(profile, company, role, seen_paths))
    if len(seen_paths) != len(profile.work):
        issues.append(_error("immutable.work_path", "Work provenance does not cover the profile.", "experience"))
    return issues


def _validate_work_entry(profile: Profile, company, role, seen_paths: set[str]) -> list[ValidationIssue]:
    work_path = role.work_path
    match = re.fullmatch(r"work\[(\d+)\]", work_path)
    if match is None:
        return [_error("immutable.work_path", "Work provenance path is invalid.", work_path)]
    index = int(match[1])
    if index >= len(profile.work) or work_path in seen_paths:
        return [_error("immutable.work_path", "Work provenance path is missing or duplicated.", work_path)]
    seen_paths.add(work_path)
    source = profile.work[index]
    return [
        _error("immutable.work_field", f"Work field '{field}' differs from the profile.", f"work[{index}].{field}")
        for field in ("company", "position", "location", "start_date", "end_date")
        if getattr(source, field) != _rendered_field(company, role, field)
    ]


def _validate_generated_text(profile: Profile, resume: ResumeDocument) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    allowed_numbers = _profile_numbers(profile)
    generated = [("headline", resume.headline.text), ("summary", resume.summary.text)]
    generated.extend(
        (f"{role.work_path}.bullets[{bullet_index}]", bullet.text)
        for role in _resume_roles(resume)
        for bullet_index, bullet in enumerate(role.bullets)
    )
    if resume.earlier_experience is not None:
        generated.extend(
            (f"earlier_experience.bullets[{index}]", bullet.text)
            for index, bullet in enumerate(resume.earlier_experience.bullets)
        )
    for path, text in generated:
        for number in _NUMBER_RE.findall(text):
            if number not in allowed_numbers:
                issues.append(
                    _error("claim.unsupported_number", f"Number '{number}' is not present in profile facts.", path)
                )
        paths = (
            next(
                (
                    bullet.fact_paths
                    for index, bullet in enumerate(resume.earlier_experience.bullets)
                    if path == f"earlier_experience.bullets[{index}]"
                ),
                (),
            )
            if path.startswith("earlier_experience.") and resume.earlier_experience is not None
            else _text_paths(resume, path)
        )
        for fact_path in paths:
            if not _fact_exists(profile, fact_path):
                issues.append(_error("claim.unknown_fact", f"Unknown provenance path '{fact_path}'.", path))
    return issues


def _validate_text_quality(profile: Profile, resume: ResumeDocument) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    starts: dict[str, str] = {}
    bullets = [
        (f"{role.work_path}.bullets[{index}]", bullet)
        for role in _resume_roles(resume)
        for index, bullet in enumerate(role.bullets)
    ]
    if resume.earlier_experience is not None:
        bullets.extend(
            (f"earlier_experience.bullets[{index}]", bullet)
            for index, bullet in enumerate(resume.earlier_experience.bullets)
        )
    for path, bullet in bullets:
        start = bullet.text.split(maxsplit=1)[0].casefold()
        if start in starts:
            issues.append(
                _warning(
                    "text.repeated_bullet_start",
                    f"Bullet starts with the same word as {starts[start]}.",
                    path,
                )
            )
        starts[start] = path
        for avoided in profile.voice.avoid:
            if avoided.casefold() in bullet.text.casefold():
                issues.append(
                    _warning(
                        "text.avoided_word",
                        f"Voice profile asks to avoid '{avoided}'.",
                        path,
                    )
                )
    return issues


def _validate_coverage(vacancy: VacancyAnalysis, covered: frozenset[str]) -> list[ValidationIssue]:
    return [
        _warning(
            "coverage.uncovered",
            f"Requirement {requirement.id} is not represented by selected evidence.",
            requirement.id,
        )
        for requirement in vacancy.requirements
        if requirement.id not in covered and requirement.priority == "must_have"
    ]


def _profile_numbers(profile: Profile) -> set[str]:
    return {number for work in profile.work for fact in work.facts for number in _NUMBER_RE.findall(fact.text)}


def _text_paths(resume: ResumeDocument, path: str) -> tuple[str, ...]:
    if path == "headline":
        return resume.headline.fact_paths
    if path == "summary":
        return resume.summary.fact_paths
    match = re.fullmatch(r"work\[(\d+)\]\.bullets\[(\d+)\]", path)
    if match is None:
        return ()
    role = next((role for role in _resume_roles(resume) if role.work_path == f"work[{match[1]}]"), None)
    return () if role is None else role.bullets[int(match[2])].fact_paths


def _resume_roles(resume: ResumeDocument) -> tuple[ResumeRole | ResumeEarlierRole, ...]:
    return tuple(role for company in resume.experience for role in company.roles)


def _rendered_work(resume: ResumeDocument):
    for company in resume.experience:
        for role in company.roles:
            yield company, role
    if resume.earlier_experience is not None:
        for role in resume.earlier_experience.source_roles:
            yield None, role


def _rendered_field(company, role, field: str):
    if field == "company":
        return role.company if hasattr(role, "company") else company.company
    if field == "location":
        return role.location if hasattr(role, "location") else company.location
    return getattr(role, field)


def _fact_exists(profile: Profile, path: str) -> bool:
    match = _FACT_PATH_RE.fullmatch(path)
    if match is None:
        return False
    work_index, fact_index = int(match["work"]), int(match["fact"])
    return work_index < len(profile.work) and fact_index < len(profile.work[work_index].facts)


def _error(code: str, message: str, path: str) -> ValidationIssue:
    return ValidationIssue(severity="error", code=code, message=message, path=path)


def _warning(code: str, message: str, path: str) -> ValidationIssue:
    return ValidationIssue(severity="warning", code=code, message=message, path=path)
