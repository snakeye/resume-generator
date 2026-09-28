import pytest

from resume_generator.config import SettingsError, load_settings


def test_load_settings_reads_dotenv_file(tmp_path):
    (tmp_path / ".env").write_text(
        "LLM_MODEL=deepseek-reasoner\nDEEPSEEK_API_KEY=from-file\nLLM_RETRIES=4\n",
        encoding="utf-8",
    )

    settings = load_settings(tmp_path)

    assert settings.llm_model == "deepseek-reasoner"
    assert settings.deepseek_api_key.get_secret_value() == "from-file"
    assert settings.llm_retries == 4


def test_process_environment_overrides_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("LLM_MODEL=from-file\n", encoding="utf-8")
    monkeypatch.setenv("LLM_MODEL", "from-environment")

    settings = load_settings(tmp_path)

    assert settings.llm_model == "from-environment"


def test_invalid_settings_have_actionable_field_path(tmp_path):
    (tmp_path / ".env").write_text("LLM_RETRIES=-1\n", encoding="utf-8")

    with pytest.raises(SettingsError, match="llm_retries"):
        load_settings(tmp_path)


def test_settings_do_not_require_deepseek_key_for_unsupported_provider(tmp_path):
    (tmp_path / ".env").write_text("LLM_PROVIDER=ollama\n", encoding="utf-8")

    settings = load_settings(tmp_path)

    assert settings.llm_provider == "ollama"
    assert settings.deepseek_api_key is None
