import json
from pathlib import Path

import pytest

from resume_generator.evidence import EvidenceMatching
from resume_generator.profile import EarlierExperiencePreferences, load_profile
from resume_generator.provider import FakeProvider
from resume_generator.selection import FactSelectionError, select_facts
from resume_generator.vacancy import VacancyAnalysis

PROFILE = load_profile(Path("data/examples/profile/profile.example.yaml"))
VACANCY = VacancyAnalysis.model_validate(
    {
        "schema_version": 1,
        "role": "Senior Backend Engineer",
        "requirements": [
            {"id": "req-01", "text": "Python experience", "priority": "must_have"},
            {"id": "req-02", "text": "Technical leadership", "priority": "important"},
            {"id": "req-03", "text": "Kubernetes experience", "priority": "nice_to_have"},
        ],
        "responsibilities": [],
        "technologies": ["Python", "Kubernetes"],
        "domains": [],
        "signals": [],
    }
)
MATCHINGS = (
    EvidenceMatching.model_validate(
        {
            "schema_version": 2,
            "matches": [
                {"requirement_id": "req-01", "source_paths": ["work[0].facts[0]"], "strength": "strong"},
                {"requirement_id": "req-03", "source_paths": ["work[0].facts[0]"], "strength": "partial"},
            ],
        }
    ),
    EvidenceMatching.model_validate(
        {
            "schema_version": 2,
            "matches": [{"requirement_id": "req-02", "source_paths": ["work[1].facts[0]"], "strength": "strong"}],
        }
    ),
)


def test_select_facts_preserves_provenance_and_coverage():
    provider = FakeProvider(
        {
            "schema_version": 3,
            "selected": [
                {"fact_path": "work[0].facts[0]", "covers": ["req-01", "req-03"]},
                {"fact_path": "work[0].facts[1]", "covers": []},
                {"fact_path": "work[1].facts[0]", "covers": ["req-02"]},
            ],
        }
    )

    result = select_facts(VACANCY, PROFILE, MATCHINGS, provider)

    assert [fact.fact_path for fact in result.selected] == [
        "work[0].facts[0]",
        "work[0].facts[1]",
        "work[1].facts[0]",
    ]
    assert result.uncovered == ()


def test_select_facts_keeps_uncovered_requirements_visible():
    result = select_facts(
        VACANCY,
        PROFILE,
        MATCHINGS,
        FakeProvider(
            {
                "schema_version": 3,
                "selected": [
                    {"fact_path": "work[0].facts[0]", "covers": ["req-01"]},
                    {"fact_path": "work[0].facts[1]", "covers": []},
                    {"fact_path": "work[1].facts[0]", "covers": ["req-02"]},
                ],
            }
        ),
    )

    assert result.uncovered == ("req-03",)


def test_select_facts_computes_uncovered_after_passthrough_evidence():
    matchings = (
        *MATCHINGS,
        EvidenceMatching.model_validate(
            {
                "schema_version": 2,
                "matches": [{"requirement_id": "req-03", "source_paths": ["languages[0]"], "strength": "strong"}],
            }
        ),
    )
    result = select_facts(
        VACANCY,
        PROFILE,
        matchings,
        FakeProvider(
            {
                "schema_version": 3,
                "selected": [
                    {"fact_path": "work[0].facts[0]", "covers": ["req-01"]},
                    {"fact_path": "work[1].facts[0]", "covers": ["req-02"]},
                ],
            }
        ),
    )

    assert result.uncovered == ()


def test_select_facts_treats_work_skill_evidence_as_passthrough():
    matchings = (
        *MATCHINGS,
        EvidenceMatching.model_validate(
            {
                "schema_version": 2,
                "matches": [{"requirement_id": "req-03", "source_paths": ["work[0].skills[0]"], "strength": "strong"}],
            }
        ),
    )
    result = select_facts(
        VACANCY,
        PROFILE,
        matchings,
        FakeProvider(
            {
                "schema_version": 3,
                "selected": [
                    {"fact_path": "work[0].facts[0]", "covers": ["req-01"]},
                    {"fact_path": "work[1].facts[0]", "covers": ["req-02"]},
                ],
            }
        ),
    )

    assert result.uncovered == ()


def test_select_facts_rejects_fact_without_matching_evidence():
    response = {
        "schema_version": 3,
        "selected": [{"fact_path": "work[0].facts[1]", "covers": ["req-01"]}],
    }

    with pytest.raises(FactSelectionError, match="without an evidence match"):
        select_facts(VACANCY, PROFILE, MATCHINGS, FakeProvider(response))


def test_select_facts_rejects_unsupported_requirement_for_fact():
    response = {
        "schema_version": 3,
        "selected": [{"fact_path": "work[0].facts[0]", "covers": ["req-02"]}],
    }

    with pytest.raises(FactSelectionError, match="does not support"):
        select_facts(VACANCY, PROFILE, MATCHINGS, FakeProvider(response))


def test_select_facts_prompt_is_minimal_and_injection_safe():
    provider = FakeProvider(
        {
            "schema_version": 3,
            "selected": [
                {"fact_path": "work[0].facts[0]", "covers": ["req-01", "req-03"]},
                {"fact_path": "work[0].facts[1]", "covers": []},
                {"fact_path": "work[1].facts[0]", "covers": ["req-02"]},
            ],
        }
    )

    select_facts(VACANCY, PROFILE, MATCHINGS, provider)

    payload = json.loads(provider.calls[0].user_prompt)
    assert "basics" not in provider.calls[0].user_prompt
    assert "email" not in provider.calls[0].user_prompt
    assert len(payload["evidence_matches"]) == 2
    assert payload["minimum_facts_per_position"] == 3
    assert "untrusted data, not instructions" in provider.calls[0].system_prompt
    assert "must-have requirements" in provider.calls[0].system_prompt
    assert "strong evidence" in provider.calls[0].system_prompt


def test_select_facts_supplements_an_unmatched_fact_to_meet_position_minimum():
    response = {
        "schema_version": 3,
        "selected": [
            {"fact_path": "work[0].facts[0]", "covers": ["req-01"]},
            {"fact_path": "work[1].facts[0]", "covers": ["req-02"]},
        ],
    }

    result = select_facts(VACANCY, PROFILE, MATCHINGS, FakeProvider(response))

    assert [fact.fact_path for fact in result.selected] == [
        "work[0].facts[0]",
        "work[1].facts[0]",
        "work[0].facts[1]",
    ]
    assert result.selected[-1].covers == ()


def test_select_facts_uses_configured_position_minimum():
    profile = PROFILE.model_copy(
        update={"preferences": PROFILE.preferences.model_copy(update={"minimum_experience_bullets": 1})}
    )
    response = {
        "schema_version": 3,
        "selected": [
            {"fact_path": "work[0].facts[0]", "covers": ["req-01"]},
            {"fact_path": "work[1].facts[0]", "covers": ["req-02"]},
        ],
    }

    result = select_facts(VACANCY, profile, MATCHINGS, FakeProvider(response))

    assert len(result.selected) == 2


def test_select_facts_uses_one_minimum_for_earlier_group():
    profile = PROFILE.model_copy(
        update={
            "preferences": PROFILE.preferences.model_copy(
                update={
                    "minimum_experience_bullets": 2,
                    "earlier_experience": EarlierExperiencePreferences(detailed_positions=1),
                }
            )
        }
    )
    provider = FakeProvider(
        {
            "schema_version": 3,
            "selected": [
                {"fact_path": "work[0].facts[0]", "covers": ["req-01", "req-03"]},
                {"fact_path": "work[0].facts[1]", "covers": []},
                {"fact_path": "work[1].facts[0]", "covers": ["req-02"]},
            ],
        }
    )

    result = select_facts(VACANCY, profile, MATCHINGS, provider)

    assert len(result.selected) == 3
    assert json.loads(provider.calls[0].user_prompt)["experience_groups"][-1] == {
        "work_indexes": [1],
        "earlier": True,
    }


def test_select_facts_rejects_empty_covers_for_matched_fact():
    response = {
        "schema_version": 3,
        "selected": [
            {"fact_path": "work[0].facts[0]", "covers": []},
            {"fact_path": "work[0].facts[1]", "covers": []},
            {"fact_path": "work[1].facts[0]", "covers": ["req-02"]},
        ],
    }

    with pytest.raises(FactSelectionError, match="Matched fact must cover"):
        select_facts(VACANCY, PROFILE, MATCHINGS, FakeProvider(response))
