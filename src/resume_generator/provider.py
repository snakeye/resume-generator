"""Structured-output boundary for language-model providers."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Protocol
from urllib import error as url_error
from urllib import request as url_request

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import DeepSeekSettings, Settings, SettingsError


class ProviderError(RuntimeError):
    """A provider failure safe to show without exposing request contents."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class ProviderModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class LLMRequest(ProviderModel):
    """Provider-independent prompt request."""

    system_prompt: str = Field(min_length=1)
    task_prompt: str = Field(min_length=1)
    user_prompt: str = Field(min_length=1)

    @field_validator("system_prompt", "task_prompt", "user_prompt")
    @classmethod
    def prompt_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class LLMUsage(ProviderModel):
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class LLMResponse(ProviderModel):
    """Normalized structured response returned to a pipeline stage."""

    payload: dict[str, Any]
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    usage: LLMUsage


class LLMProvider(Protocol):
    def generate_json(self, request: LLMRequest) -> LLMResponse: ...


HttpResponse = Any
HttpTransport = Callable[[url_request.Request, float], HttpResponse]
Sleep = Callable[[float], None]


class DeepSeekProvider:
    """DeepSeek chat-completions adapter with conservative retries."""

    provider_name = "deepseek"

    def __init__(
        self,
        settings: DeepSeekSettings,
        *,
        transport: HttpTransport | None = None,
        sleep: Sleep = time.sleep,
    ) -> None:
        self.api_key = settings.api_key.get_secret_value()
        self.model = settings.model
        self.endpoint = str(settings.endpoint)
        self.timeout = settings.timeout
        self.retries = settings.retries
        self._transport = transport or _urlopen_transport
        self._sleep = sleep
        self._debug_directory: Path | None = None
        self._debug_response_number = 0

    def set_debug_directory(self, directory: Path) -> None:
        """Enable local response capture for one pipeline run."""
        self._debug_directory = directory
        self._debug_response_number = 0

    def generate_json(self, request: LLMRequest) -> LLMResponse:
        model = self.model
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.task_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        encoded = _json_bytes(body)

        for attempt in range(self.retries + 1):
            try:
                raw_response = self._transport(self._build_request(encoded), self.timeout)
                response_data = _read_json_response(raw_response)
                self._save_debug_response(response_data)
                return _parse_response(response_data, model=model)
            except ProviderError as error:
                if not error.retryable or attempt == self.retries:
                    raise
                self._sleep(2**attempt)
            except url_error.HTTPError as error:
                retryable = error.code == 429 or error.code >= 500
                if not retryable or attempt == self.retries:
                    raise ProviderError(f"DeepSeek returned HTTP {error.code}.", retryable=retryable) from error
                self._sleep(2**attempt)
            except (TimeoutError, url_error.URLError) as error:
                if attempt == self.retries:
                    raise ProviderError("DeepSeek request failed after retries.", retryable=True) from error
                self._sleep(2**attempt)
        raise ProviderError("DeepSeek request failed.", retryable=True)

    def _save_debug_response(self, response_data: Mapping[str, Any]) -> None:
        if self._debug_directory is None:
            return
        self._debug_response_number += 1
        path = self._debug_directory / f"deepseek-response-{self._debug_response_number:03d}.json"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(response_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError as error:
            raise ProviderError("Cannot save DeepSeek debug response.") from error

    def _build_request(self, body: bytes) -> url_request.Request:
        return url_request.Request(
            self.endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )


@dataclass
class FakeProvider:
    """Deterministic provider for unit and contract tests."""

    response: Mapping[str, Any]
    model: str = "fake-model"
    calls: list[LLMRequest] | None = None

    def generate_json(self, request: LLMRequest) -> LLMResponse:
        if self.calls is None:
            self.calls = []
        self.calls.append(request)
        return LLMResponse(payload=dict(self.response), provider="fake", model=self.model, usage=LLMUsage())


class UnsupportedProvider:
    """Explicit placeholder for providers outside the first release."""

    def __init__(self, name: str) -> None:
        self.name = name

    def generate_json(self, request: LLMRequest) -> LLMResponse:
        raise ProviderError(f"LLM provider '{self.name}' is not supported. Use provider 'deepseek'.")


def create_provider(
    settings: Settings,
) -> LLMProvider:
    """Create the configured provider without reading process state."""
    if settings.llm_provider != "deepseek":
        return UnsupportedProvider(settings.llm_provider)
    try:
        provider_settings = DeepSeekSettings.from_settings(settings)
    except SettingsError as error:
        raise ProviderError(str(error)) from error
    return DeepSeekProvider(provider_settings)


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ProviderError("Provider request is not valid JSON.") from error


def _urlopen_transport(request: url_request.Request, timeout: float) -> HttpResponse:
    return url_request.urlopen(request, timeout=timeout)


def _read_json_response(response: HttpResponse) -> Mapping[str, Any]:
    try:
        status = getattr(response, "status", 200)
        if status == 429 or status >= 500:
            raise ProviderError(f"DeepSeek returned HTTP {status}.", retryable=True)
        if status >= 400:
            raise ProviderError(f"DeepSeek returned HTTP {status}.")
        raw = response.read()
        value = json.loads(raw.decode("utf-8"))
    except url_error.HTTPError as error:
        retryable = error.code == 429 or error.code >= 500
        raise ProviderError(f"DeepSeek returned HTTP {error.code}.", retryable=retryable) from error
    except (UnicodeDecodeError, JSONDecodeError) as error:
        raise ProviderError("DeepSeek returned invalid JSON.") from error
    if not isinstance(value, Mapping):
        raise ProviderError("DeepSeek returned a JSON value instead of an object.")
    return value


def _parse_response(value: Mapping[str, Any], *, model: str) -> LLMResponse:
    if "error" in value:
        raise ProviderError("DeepSeek returned an API error.")
    try:
        choice = value["choices"][0]
        content = choice["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise ProviderError("DeepSeek response is missing generated content.") from error
    if not isinstance(content, str):
        raise ProviderError("DeepSeek generated content is not text.")
    try:
        payload = json.loads(content)
    except JSONDecodeError as error:
        raise ProviderError("DeepSeek generated invalid JSON.") from error
    if not isinstance(payload, Mapping):
        raise ProviderError("DeepSeek generated JSON must be an object.")
    return LLMResponse(
        payload=dict(payload),
        provider="deepseek",
        model=value.get("model", model),
        usage=_parse_usage(value.get("usage")),
    )


def _parse_usage(value: Any) -> LLMUsage:
    if not isinstance(value, Mapping):
        return LLMUsage()
    return LLMUsage(
        prompt_tokens=_optional_int(value.get("prompt_tokens")),
        completion_tokens=_optional_int(value.get("completion_tokens")),
        total_tokens=_optional_int(value.get("total_tokens")),
    )


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
