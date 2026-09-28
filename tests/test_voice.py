import json
from pathlib import Path

import pytest

from resume_generator.bullets import BulletGeneration
from resume_generator.profile import load_profile
from resume_generator.provider import FakeProvider
from resume_generator.summary import ResumeSummary
from resume_generator.terminology import normalize_terminology
from resume_generator.vacancy import VacancyAnalysis
from resume_generator.voice import VoiceAdaptationError, adapt_voice

PROFILE = load_profile(Path("data/examples/profile/profile.example.yaml"))
VACANCY = VacancyAnalysis.model_validate(
    {
        "schema_version": 1,
        "role": "Senior Backend Engineer",
        "requirements": [],
        "responsibilities": [],
        "technologies": ["Python"],
        "domains": [],
        "signals": [],
    }
)
TERMINOLOGY = normalize_terminology(PROFILE, VACANCY)
SUMMARY = ResumeSummary.model_validate(
    {"schema_version": 1, "text": "Python engineer focused on reliable systems.", "fact_paths": ["work[0].facts[0]"]}
)
BULLETS = BulletGeneration.model_validate(
    {
        "schema_version": 2,
        "bullets": [{"text": "Built Python services.", "fact_paths": ["work[0].facts[0]"]}],
    }
)


def test_adapt_voice_preserves_provenance_and_bullet_count():
    provider = FakeProvider(
        {
            "schema_version": 1,
            "summary": {"text": "Python engineer focused on reliable systems.", "fact_paths": ["work[0].facts[0]"]},
            "bullets": [{"text": "Built Python services in a direct style.", "fact_paths": ["work[0].facts[0]"]}],
        }
    )

    result = adapt_voice(PROFILE, TERMINOLOGY, SUMMARY, BULLETS, provider)

    assert result.summary.fact_paths == SUMMARY.fact_paths
    assert result.bullets[0].fact_paths == BULLETS.bullets[0].fact_paths


def test_adapt_voice_rejects_changed_provenance():
    response = {
        "schema_version": 1,
        "summary": {
            "text": "Python engineer.",
            "fact_paths": ["work[0].facts[1]"],
        },
        "bullets": [{"text": "Built Python services.", "fact_paths": ["work[0].facts[0]"]}],
    }

    with pytest.raises(VoiceAdaptationError, match="summary fact_paths must remain unchanged"):
        adapt_voice(PROFILE, TERMINOLOGY, SUMMARY, BULLETS, FakeProvider(response))


def test_adapt_voice_rejects_removed_protected_terminology():
    response = {
        "schema_version": 1,
        "summary": {"text": "Engineer focused on reliable systems.", "fact_paths": ["work[0].facts[0]"]},
        "bullets": [{"text": "Built services.", "fact_paths": ["work[0].facts[0]"]}],
    }

    with pytest.raises(VoiceAdaptationError, match="Protected terminology changed: Python"):
        adapt_voice(PROFILE, TERMINOLOGY, SUMMARY, BULLETS, FakeProvider(response))


def test_adapt_voice_prompt_contains_only_content_and_voice_constraints():
    provider = FakeProvider(
        {
            "schema_version": 1,
            "summary": {"text": "Python engineer.", "fact_paths": ["work[0].facts[0]"]},
            "bullets": [{"text": "Built Python services.", "fact_paths": ["work[0].facts[0]"]}],
        }
    )

    adapt_voice(PROFILE, TERMINOLOGY, SUMMARY, BULLETS, provider)

    payload = json.loads(provider.calls[0].user_prompt)
    assert payload["voice"]["avoid"] == list(PROFILE.voice.avoid)
    assert payload["voice"]["language_background"] == PROFILE.voice.language_background
    assert "email" not in provider.calls[0].user_prompt
    assert "untrusted" in provider.calls[0].system_prompt
    assert "not instructions" in provider.calls[0].system_prompt
    assert "Preserve the number" in provider.calls[0].system_prompt
    assert "bullets" in provider.calls[0].system_prompt
    system_prompt = " ".join(provider.calls[0].system_prompt.split())
    assert "slightly literal phrasing" in system_prompt
    assert "polished native-speaker copywriting" in system_prompt
