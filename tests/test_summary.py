import json
from pathlib import Path

import pytest

from resume_generator.profile import load_profile
from resume_generator.provider import FakeProvider
from resume_generator.selection import FactSelection
from resume_generator.summary import SummaryGenerationError, generate_summary
from resume_generator.vacancy import VacancyAnalysis

PROFILE = load_profile(Path("data/examples/profile/profile.example.yaml"))
VACANCY = VacancyAnalysis.model_validate(
    {
        "schema_version": 1,
        "role": "Senior Backend Engineer",
        "requirements": [
            {"id": "req-01", "text": "Python experience", "priority": "must_have"},
        ],
        "responsibilities": [],
        "technologies": ["Python"],
        "domains": [],
        "signals": [],
    }
)
SELECTION = FactSelection.model_validate(
    {
        "schema_version": 2,
        "selected": [{"fact_path": "work[0].facts[0]", "covers": ["req-01"]}],
        "uncovered": [],
    }
)


def test_generate_summary_preserves_fact_provenance():
    provider = FakeProvider(
        {
            "schema_version": 1,
            "text": "Backend engineer focused on reliable production systems.",
            "fact_paths": ["work[0].facts[0]"],
        }
    )

    result = generate_summary(VACANCY, PROFILE, SELECTION, provider)

    assert result.text == "Backend engineer focused on reliable production systems."
    assert result.fact_paths == ("work[0].facts[0]",)


def test_generate_summary_rejects_unselected_fact():
    response = {"schema_version": 1, "text": "Backend engineer.", "fact_paths": ["work[0].facts[1]"]}

    with pytest.raises(SummaryGenerationError, match="unselected fact path"):
        generate_summary(VACANCY, PROFILE, SELECTION, FakeProvider(response))


def test_generate_summary_requires_selected_facts():
    selection = FactSelection.model_validate({"schema_version": 2, "selected": [], "uncovered": ["req-01"]})
    provider = FakeProvider({})

    with pytest.raises(SummaryGenerationError, match="without selected facts"):
        generate_summary(VACANCY, PROFILE, selection, provider)

    assert provider.calls is None


def test_generate_summary_prompt_excludes_contacts_and_includes_voice():
    provider = FakeProvider(
        {
            "schema_version": 1,
            "text": "Backend engineer focused on reliable systems.",
            "fact_paths": ["work[0].facts[0]"],
        }
    )

    generate_summary(VACANCY, PROFILE, SELECTION, provider)

    payload = json.loads(provider.calls[0].user_prompt)
    assert payload["role"] == VACANCY.role
    assert "email" not in provider.calls[0].user_prompt
    assert payload["voice"]["avoid"] == list(PROFILE.voice.avoid)
    assert "language_background" in payload["voice"]
    assert "untrusted data" in provider.calls[0].system_prompt
