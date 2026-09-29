"""Loading, validating, and normalizing the local professional profile."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class ProfileError(ValueError):
    """Raised when the profile does not satisfy its data contract."""


class ProfileModel(BaseModel):
    """Strict immutable base for user-controlled profile data."""

    model_config = ConfigDict(extra="forbid", strict=False, frozen=True)


def _date_value(value: Any) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str) or not re.fullmatch(r"(?:\d{4}|\d{4}-\d{2})", value):
        raise ValueError("must use YYYY or YYYY-MM format")
    if "-" in value and not 1 <= int(value[5:]) <= 12:
        raise ValueError("must contain a month from 01 to 12")
    return value


def _optional_date_value(value: Any) -> str | None:
    return None if value is None else _date_value(value)


class Link(ProfileModel):
    label: str = Field(min_length=1)
    url: str = Field(min_length=1)


class Basics(ProfileModel):
    name: str = Field(min_length=1)
    email: str = Field(min_length=1)
    phone: str | None = None
    location: str | None = None
    links: tuple[Link, ...] = ()


class Fact(ProfileModel):
    text: str = Field(min_length=1)

    @field_validator("text", mode="before")
    @classmethod
    def validate_text(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("must be a non-empty string")
        return value

    @model_validator(mode="before")
    @classmethod
    def normalize_fact(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"text": value}
        if isinstance(value, dict):
            return {"text": value}
        return value


class Work(ProfileModel):
    company: str = Field(min_length=1)
    position: str = Field(min_length=1)
    location: str | None = None
    start_date: str
    end_date: str | None = None
    skills: tuple[str, ...] = ()
    facts: tuple[Fact, ...] = Field(min_length=1)

    _validate_start_date = field_validator("start_date", mode="before")(_date_value)
    _validate_end_date = field_validator("end_date", mode="before")(_optional_date_value)

    @model_validator(mode="after")
    def validate_date_order(self) -> Work:
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("must not be earlier than start_date")
        return self


class SkillGroup(ProfileModel):
    name: str = Field(min_length=1)
    keywords: tuple[str, ...] = Field(min_length=1)


class Education(ProfileModel):
    institution: str = Field(min_length=1)
    area: str | None = None
    study_type: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    details: tuple[str, ...] = ()

    _validate_start_date = field_validator("start_date", mode="before")(_optional_date_value)
    _validate_end_date = field_validator("end_date", mode="before")(_optional_date_value)

    @model_validator(mode="after")
    def validate_date_order(self) -> Education:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("must not be earlier than start_date")
        return self


class Language(ProfileModel):
    language: str = Field(min_length=1)
    level: str = Field(min_length=1)


class EarlierExperiencePreferences(ProfileModel):
    detailed_positions: int | None = Field(default=None, strict=True, ge=1)
    ending_before: str | None = None

    _validate_ending_before = field_validator("ending_before", mode="before")(_optional_date_value)

    @model_validator(mode="after")
    def validate_selector(self) -> EarlierExperiencePreferences:
        if self.detailed_positions is None and self.ending_before is None:
            raise ValueError("must define detailed_positions or ending_before")
        if self.detailed_positions is not None and self.ending_before is not None:
            raise ValueError("must define only one of detailed_positions or ending_before")
        return self


class Preferences(ProfileModel):
    minimum_experience_bullets: int = Field(default=3, strict=True, ge=1)
    earlier_experience: EarlierExperiencePreferences | None = None


class Voice(ProfileModel):
    concise: bool | None = Field(default=None, strict=True)
    first_person: bool | None = Field(default=None, strict=True)
    language_background: str | None = Field(default=None, min_length=1)
    avoid: tuple[str, ...] = ()

    @field_validator("language_background")
    @classmethod
    def validate_language_background(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value


class Profile(ProfileModel):
    schema_version: int = Field(..., strict=True)
    basics: Basics
    work: tuple[Work, ...] = Field(min_length=1)
    education: tuple[Education, ...] = ()
    skills: tuple[str, ...] = ()
    skill_groups: tuple[SkillGroup, ...] = ()
    languages: tuple[Language, ...] = ()
    preferences: Preferences = Preferences()
    aliases: dict[str, tuple[str, ...]] = {}
    voice: Voice = Voice()

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError("must be 1")
        return value


def parse_profile(
    data: Any,
    *,
    preferences: Any | None = None,
    aliases: Any | None = None,
    voice: Any | None = None,
) -> Profile:
    """Validate parsed YAML and return the normalized Pydantic model."""
    if not isinstance(data, dict):
        raise ProfileError("profile: must be a mapping")
    values = dict(data)
    values["preferences"] = {} if preferences is None else preferences
    values["aliases"] = {} if aliases is None else aliases
    values["voice"] = {} if voice is None else voice
    try:
        return Profile.model_validate(values)
    except ValidationError as error:
        raise ProfileError(_format_validation_error(error)) from error


def load_profile(path: Path) -> Profile:
    """Load and validate the profile and its optional sibling configs."""
    root = _load_yaml(path)
    directory = path.parent
    example_suffix = ".example" if path.name.endswith(".example.yaml") else ""
    return parse_profile(
        root,
        preferences=_load_optional_yaml(directory / f"preferences{example_suffix}.yaml"),
        aliases=_load_optional_yaml(directory / f"aliases{example_suffix}.yaml"),
        voice=_load_optional_yaml(directory / f"voice{example_suffix}.yaml"),
    )


def _load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ProfileError(f"{path}: file does not exist; run ./resume setup") from error
    except OSError as error:
        raise ProfileError(f"{path}: cannot be read ({error})") from error
    except yaml.YAMLError as error:
        raise ProfileError(f"{path}: invalid YAML ({error})") from error


def _load_optional_yaml(path: Path) -> Any:
    if not path.exists():
        return None
    return _load_yaml(path)


def _format_validation_error(error: ValidationError) -> str:
    errors = error.errors()
    first = next((item for item in errors if item["type"] == "extra_forbidden"), errors[0])
    path = "profile" + "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in first["loc"])
    if first["type"] == "extra_forbidden":
        return f"{path}: unknown field {first['loc'][-1]!r}"
    return f"{path}: {first['msg']}"
