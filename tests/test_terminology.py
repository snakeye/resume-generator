from pathlib import Path

import pytest

from resume_generator.profile import load_profile
from resume_generator.terminology import TerminologyError, normalize_terminology
from resume_generator.vacancy import VacancyAnalysis

PROFILE = load_profile(Path("data/examples/profile/profile.example.yaml"))
VACANCY = VacancyAnalysis.model_validate(
    {
        "schema_version": 1,
        "role": "Senior Backend Engineer",
        "requirements": [],
        "responsibilities": [],
        "technologies": ["Postgres", "K8s", "Rust", "Python"],
        "domains": ["Event-driven systems"],
        "signals": ["Technical Leadership"],
    }
)


def test_normalize_terminology_resolves_aliases_and_marks_profile_matches():
    result = normalize_terminology(PROFILE, VACANCY)

    terms = {(term.source, term.canonical): term.profile_match for term in result.vacancy_terms}

    assert terms[("Postgres", "postgresql")] is True
    assert terms[("K8s", "kubernetes")] is False
    assert terms[("Rust", "rust")] is False
    assert terms[("Python", "python")] is True


def test_normalize_terminology_deduplicates_profile_terms():
    result = normalize_terminology(PROFILE, VACANCY)

    assert result.profile_terms.count("python") == 1
    assert "apache kafka" in result.profile_terms


def test_normalize_terminology_deduplicates_vacancy_terms_by_category():
    vacancy = VACANCY.model_copy(update={"technologies": ("Postgres", "postgresql")})

    result = normalize_terminology(PROFILE, vacancy)

    assert len([term for term in result.vacancy_terms if term.canonical == "postgresql"]) == 1


def test_normalize_terminology_rejects_ambiguous_aliases():
    profile = PROFILE.model_copy(update={"aliases": {"python": ("py",), "pytorch": ("py",)}})

    with pytest.raises(TerminologyError, match="multiple canonical terms"):
        normalize_terminology(profile, VACANCY)
