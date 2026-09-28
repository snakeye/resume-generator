"""Candidate voice adaptation without changing content provenance."""

from __future__ import annotations

import json
from importlib import resources
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .bullets import BulletGeneration, ResumeBullet
from .profile import Profile
from .provider import LLMProvider, LLMRequest
from .summary import ResumeSummary
from .terminology import TerminologyAnalysis


class VoiceAdaptationError(ValueError):
    """Raised when voice adaptation changes content provenance or terminology."""


class AdaptedText(BaseModel):
    """One adapted text value with unchanged source fact paths."""

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


class VoiceAdaptation(BaseModel):
    """Versioned output of voice adaptation."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal[1]
    summary: AdaptedText
    bullets: tuple[AdaptedText, ...]

    @field_validator("bullets", mode="before")
    @classmethod
    def normalize_bullets(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


def adapt_voice(
    profile: Profile,
    terminology: TerminologyAnalysis,
    summary: ResumeSummary,
    bullets: BulletGeneration,
    provider: LLMProvider,
) -> VoiceAdaptation:
    """Adapt generated text to candidate voice without changing its evidence."""
    response = provider.generate_json(
        LLMRequest(
            system_prompt=_system_prompt(),
            task_prompt=_task_prompt(),
            user_prompt=_user_prompt(profile, terminology, summary, bullets),
        )
    )
    try:
        result = VoiceAdaptation.model_validate(response.payload)
        _validate_output(result, terminology, summary, bullets)
    except (ValidationError, VoiceAdaptationError) as error:
        if isinstance(error, VoiceAdaptationError):
            raise
        first = error.errors()[0]
        path = ".".join(str(part) for part in first["loc"]) or "voice"
        raise VoiceAdaptationError(f"Voice adaptation field {path}: {first['msg']}") from error
    return result


def _validate_output(
    result: VoiceAdaptation,
    terminology: TerminologyAnalysis,
    summary: ResumeSummary,
    bullets: BulletGeneration,
) -> None:
    _validate_text_provenance(result.summary, summary, "summary")
    if len(result.bullets) != len(bullets.bullets):
        raise VoiceAdaptationError("Voice adaptation must preserve the number of bullets")
    for index, (adapted, original) in enumerate(zip(result.bullets, bullets.bullets, strict=True)):
        _validate_text_provenance(adapted, original, f"bullet {index}")
    _validate_protected_terms(result.summary.text, summary.text, terminology)
    for adapted, original in zip(result.bullets, bullets.bullets, strict=True):
        _validate_protected_terms(adapted.text, original.text, terminology)


def _validate_text_provenance(adapted: AdaptedText, original: ResumeSummary | ResumeBullet, label: str) -> None:
    if len(adapted.fact_paths) != len(set(adapted.fact_paths)):
        raise VoiceAdaptationError(f"{label} fact_paths must not contain duplicates")
    if set(adapted.fact_paths) != set(original.fact_paths):
        raise VoiceAdaptationError(f"{label} fact_paths must remain unchanged")


def _validate_protected_terms(adapted: str, original: str, terminology: TerminologyAnalysis) -> None:
    for term in terminology.vacancy_terms:
        if not term.profile_match:
            continue
        if term.source.casefold() in original.casefold() and term.source.casefold() not in adapted.casefold():
            raise VoiceAdaptationError(f"Protected terminology changed: {term.source}")


def _system_prompt() -> str:
    return (
        resources.files("resume_generator.resources")
        .joinpath("prompts/voice-adaptation/system.md")
        .read_text(encoding="utf-8")
    )


def _task_prompt() -> str:
    return (
        resources.files("resume_generator.resources")
        .joinpath("prompts/voice-adaptation/task.md")
        .read_text(encoding="utf-8")
    )


def _user_prompt(
    profile: Profile,
    terminology: TerminologyAnalysis,
    summary: ResumeSummary,
    bullets: BulletGeneration,
) -> str:
    return json.dumps(
        {
            "voice": profile.voice.model_dump(mode="json"),
            "protected_terminology": [term.source for term in terminology.vacancy_terms if term.profile_match],
            "summary": summary.model_dump(mode="json"),
            "bullets": bullets.model_dump(mode="json"),
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
