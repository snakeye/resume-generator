"""Validated application settings loaded from environment and .env."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    PositiveFloat,
    SecretStr,
    ValidationError,
    field_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class SettingsError(RuntimeError):
    """Raised when application configuration cannot be parsed safely."""


class DeepSeekSettings(BaseModel):
    """Validated settings required by the DeepSeek adapter."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    api_key: SecretStr
    model: str = Field(min_length=1)
    endpoint: AnyHttpUrl
    timeout: PositiveFloat
    retries: NonNegativeInt

    @field_validator("model")
    @classmethod
    def model_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @classmethod
    def from_settings(cls, settings: Settings) -> DeepSeekSettings:
        if settings.deepseek_api_key is None or not settings.deepseek_api_key.get_secret_value().strip():
            raise SettingsError("DEEPSEEK_API_KEY is not configured.")
        try:
            return cls(
                api_key=settings.deepseek_api_key,
                model=settings.llm_model,
                endpoint=settings.deepseek_endpoint,
                timeout=settings.llm_timeout_seconds,
                retries=settings.llm_retries,
            )
        except ValidationError as error:
            first = error.errors()[0]
            path = ".".join(str(part) for part in first["loc"]) or "deepseek"
            raise SettingsError(f"{path}: {first['msg']}") from error


class Settings(BaseSettings):
    """Application configuration with environment variables as the interface."""

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    llm_provider: Literal["deepseek", "openai", "ollama"] = "deepseek"
    llm_model: str = "deepseek-chat"
    deepseek_api_key: SecretStr | None = None
    deepseek_endpoint: AnyHttpUrl = AnyHttpUrl("https://api.deepseek.com/chat/completions")
    llm_timeout_seconds: PositiveFloat = 60.0
    llm_retries: NonNegativeInt = 2


def load_settings(root: Path) -> Settings:
    """Load settings from the repository .env and the process environment."""
    try:
        return Settings(_env_file=root / ".env")
    except ValidationError as error:
        first = error.errors()[0]
        path = ".".join(str(part) for part in first["loc"]) or "settings"
        raise SettingsError(f"{path}: {first['msg']}") from error


def has_required_provider_secret(settings: Settings) -> bool:
    """Return whether the selected provider has its required secret configured."""
    if settings.llm_provider != "deepseek":
        return True
    try:
        DeepSeekSettings.from_settings(settings)
    except SettingsError:
        return False
    return True
