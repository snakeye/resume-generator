import json
from pathlib import Path

import pytest

from resume_generator.bullets import BulletGenerationError, generate_bullets
from resume_generator.profile import load_profile
from resume_generator.provider import FakeProvider
from resume_generator.selection import FactSelection
from resume_generator.terminology import TerminologyAnalysis
from resume_generator.vacancy import VacancyAnalysis

EXAMPLE_PROFILE = load_profile(Path("data/examples/profile/profile.example.yaml"))
PROFILE = EXAMPLE_PROFILE.model_copy(
    update={
        "work": EXAMPLE_PROFILE.work[:1],
        "preferences": EXAMPLE_PROFILE.preferences.model_copy(update={"minimum_experience_bullets": 1}),
    }
)
VACANCY = VacancyAnalysis.model_validate(
    {
        "schema_version": 1,
        "role": "Senior Backend Engineer",
        "requirements": [
            {"id": "req-01", "text": "Python experience", "priority": "must_have"},
            {"id": "req-02", "text": "Reliable production systems", "priority": "important"},
        ],
        "responsibilities": [],
        "technologies": ["Python"],
        "domains": ["Production systems"],
        "signals": [],
    }
)
TERMINOLOGY = TerminologyAnalysis.model_validate(
    {
        "schema_version": 1,
        "profile_terms": ("python", "postgresql"),
        "vacancy_terms": (
            {"category": "technology", "source": "Python", "canonical": "python", "profile_match": True},
        ),
    }
)
SELECTION = FactSelection.model_validate(
    {
        "schema_version": 2,
        "selected": [{"fact_path": "work[0].facts[0]", "covers": ["req-01", "req-02"]}],
        "uncovered": [],
    }
)


def test_generate_bullets_preserves_fact_provenance():
    provider = FakeProvider(
        {
            "schema_version": 2,
            "bullets": [
                {
                    "text": "Reduced API response time by 35% by redesigning database access.",
                    "fact_paths": ["work[0].facts[0]"],
                }
            ],
        }
    )

    result = generate_bullets(VACANCY, TERMINOLOGY, PROFILE, SELECTION, provider)

    assert result.bullets[0].fact_paths == ("work[0].facts[0]",)


def test_generate_bullets_rejects_unselected_fact():
    response = {
        "schema_version": 2,
        "bullets": [{"text": "Built reliable services.", "fact_paths": ["work[0].facts[1]"]}],
    }

    with pytest.raises(BulletGenerationError, match="unselected fact path"):
        generate_bullets(VACANCY, TERMINOLOGY, PROFILE, SELECTION, FakeProvider(response))


def test_generate_bullets_rejects_duplicate_fact_paths():
    response = {
        "schema_version": 2,
        "bullets": [
            {
                "text": "Reduced API response time.",
                "fact_paths": ["work[0].facts[0]", "work[0].facts[0]"],
            }
        ],
    }

    with pytest.raises(BulletGenerationError, match="must not contain duplicates"):
        generate_bullets(VACANCY, TERMINOLOGY, PROFILE, SELECTION, FakeProvider(response))


def test_generate_bullets_prompt_contains_only_relevant_stage_inputs():
    provider = FakeProvider(
        {
            "schema_version": 2,
            "bullets": [
                {
                    "text": "Reduced API response time by 35% by redesigning database access.",
                    "fact_paths": ["work[0].facts[0]"],
                }
            ],
        }
    )

    generate_bullets(VACANCY, TERMINOLOGY, PROFILE, SELECTION, provider)

    payload = json.loads(provider.calls[0].user_prompt)
    assert [requirement["id"] for requirement in payload["requirements"]] == ["req-01", "req-02"]
    assert payload["minimum_bullets_per_position"] == 1
    assert "email" not in provider.calls[0].user_prompt
    assert payload["voice"]["avoid"] == list(PROFILE.voice.avoid)
    assert payload["voice"]["language_background"] == PROFILE.voice.language_background
    assert "untrusted data" in provider.calls[0].system_prompt
    assert "Do not add" in provider.calls[0].system_prompt
    system_prompt = " ".join(provider.calls[0].system_prompt.split())
    assert "slightly literal phrasing when requested" in system_prompt
    assert "polished native-speaker copywriting" in system_prompt


def test_generate_bullets_rejects_output_below_configured_minimum():
    selection = FactSelection.model_validate(
        {
            "schema_version": 2,
            "selected": [
                {"fact_path": "work[0].facts[0]", "covers": ["req-01", "req-02"]},
                {"fact_path": "work[0].facts[1]", "covers": []},
                {"fact_path": "work[1].facts[0]", "covers": []},
            ],
            "uncovered": [],
        }
    )
    response = {
        "schema_version": 2,
        "bullets": [
            {
                "text": "Improved API performance and led technical planning.",
                "fact_paths": ["work[0].facts[0]", "work[0].facts[1]"],
            },
            {"text": "Built event-driven services.", "fact_paths": ["work[1].facts[0]"]},
        ],
    }

    with pytest.raises(BulletGenerationError, match=r"work\[0\] requires at least 2 bullet"):
        generate_bullets(VACANCY, TERMINOLOGY, EXAMPLE_PROFILE, selection, FakeProvider(response))


def test_generate_bullets_rejects_selected_fact_missing_from_output():
    selection = FactSelection.model_validate(
        {
            "schema_version": 2,
            "selected": [
                {"fact_path": "work[0].facts[0]", "covers": ["req-01", "req-02"]},
                {"fact_path": "work[0].facts[1]", "covers": []},
            ],
            "uncovered": [],
        }
    )
    response = {
        "schema_version": 2,
        "bullets": [{"text": "Improved API performance.", "fact_paths": ["work[0].facts[0]"]}],
    }

    with pytest.raises(BulletGenerationError, match="missing from bullets"):
        generate_bullets(VACANCY, TERMINOLOGY, PROFILE, selection, FakeProvider(response))


def test_generate_bullets_rejects_cross_position_bullet():
    selection = FactSelection.model_validate(
        {
            "schema_version": 2,
            "selected": [
                {"fact_path": "work[0].facts[0]", "covers": ["req-01", "req-02"]},
                {"fact_path": "work[1].facts[0]", "covers": []},
            ],
            "uncovered": [],
        }
    )
    response = {
        "schema_version": 2,
        "bullets": [
            {
                "text": "Improved APIs and built event-driven services.",
                "fact_paths": ["work[0].facts[0]", "work[1].facts[0]"],
            }
        ],
    }

    with pytest.raises(BulletGenerationError, match="cannot combine facts"):
        generate_bullets(VACANCY, TERMINOLOGY, EXAMPLE_PROFILE, selection, FakeProvider(response))
