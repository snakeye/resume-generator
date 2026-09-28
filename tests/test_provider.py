import io
import json
from urllib.error import HTTPError

import pytest

from resume_generator.config import DeepSeekSettings, Settings
from resume_generator.provider import (
    DeepSeekProvider,
    FakeProvider,
    LLMRequest,
    ProviderError,
    create_provider,
)


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body


def request():
    return LLMRequest(system_prompt="Return JSON.", task_prompt="Analyze this vacancy.", user_prompt='{"ok": true}')


def deepseek_settings():
    return DeepSeekSettings.from_settings(Settings(_env_file=None, deepseek_api_key="secret"))


def test_fake_provider_returns_structured_payload_and_records_request():
    provider = FakeProvider({"requirements": []})

    response = provider.generate_json(request())

    assert response.payload == {"requirements": []}
    assert provider.calls == [request()]


def test_deepseek_provider_sends_json_request_and_normalizes_usage():
    captured = []

    def transport(http_request, timeout):
        captured.append((json.loads(http_request.data), timeout, http_request.headers["Authorization"]))
        return FakeResponse(
            {
                "model": "deepseek-chat",
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7},
            }
        )

    response = DeepSeekProvider(deepseek_settings(), transport=transport, sleep=lambda _: None).generate_json(request())

    assert response.payload == {"ok": True}
    assert response.model == "deepseek-chat"
    assert [message["role"] for message in captured[0][0]["messages"]] == ["system", "user", "user"]
    assert captured[0][0]["messages"][1]["content"] == "Analyze this vacancy."
    assert captured[0][0]["messages"][2]["content"] == '{"ok": true}'
    assert captured[0][0]["temperature"] == 0
    assert captured[0][0]["response_format"] == {"type": "json_object"}
    assert captured[0][2] == "Bearer secret"


def test_deepseek_provider_retries_rate_limit():
    attempts = []

    def transport(http_request, timeout):
        attempts.append(1)
        if len(attempts) == 1:
            raise HTTPError("https://example.test", 429, "rate limit", {}, io.BytesIO())
        return FakeResponse({"choices": [{"message": {"content": "{}"}}]})

    settings = DeepSeekSettings.from_settings(Settings(_env_file=None, deepseek_api_key="secret", llm_retries=1))
    response = DeepSeekProvider(settings, transport=transport, sleep=lambda _: None).generate_json(request())

    assert response.payload == {}
    assert len(attempts) == 2


def test_deepseek_provider_saves_response_for_debugging(tmp_path):
    provider = DeepSeekProvider(
        deepseek_settings(),
        transport=lambda http_request, timeout: FakeResponse(
            {"choices": [{"message": {"content": '{"schema_version": 1, "invalid": true}'}}]}
        ),
    )
    provider.set_debug_directory(tmp_path)

    provider.generate_json(request())

    saved = json.loads((tmp_path / "deepseek-response-001.json").read_text(encoding="utf-8"))
    assert json.loads(saved["choices"][0]["message"]["content"])["invalid"] is True
    assert "Authorization" not in json.dumps(saved)
    assert "secret" not in json.dumps(saved)


def test_deepseek_provider_rejects_invalid_generated_json_without_leaking_prompt():
    provider = DeepSeekProvider(
        deepseek_settings(),
        transport=lambda http_request, timeout: FakeResponse({"choices": [{"message": {"content": "not json"}}]}),
    )

    with pytest.raises(ProviderError, match="generated invalid JSON") as raised:
        provider.generate_json(
            LLMRequest(system_prompt="system secret", task_prompt="task secret", user_prompt="user secret")
        )

    assert "secret" not in str(raised.value)


def test_create_provider_does_not_silently_fallback():
    provider = create_provider(Settings(_env_file=None, llm_provider="ollama"))

    with pytest.raises(ProviderError, match="not supported"):
        provider.generate_json(request())


def test_create_deepseek_requires_api_key():
    with pytest.raises(ProviderError, match="DEEPSEEK_API_KEY"):
        create_provider(Settings(_env_file=None))
