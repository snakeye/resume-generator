from pathlib import Path

from resume_generator.profile import load_profile
from resume_generator.skills import select_skills
from resume_generator.terminology import normalize_terminology
from resume_generator.vacancy import VacancyAnalysis

PROFILE = load_profile(Path("data/examples/profile/profile.example.yaml"))
VACANCY = VacancyAnalysis.model_validate(
    {
        "schema_version": 1,
        "role": "Senior Backend Engineer",
        "requirements": [],
        "responsibilities": [],
        "technologies": ["Postgres", "K8s", "Python", "PostgreSQL"],
        "domains": ["Technical Leadership"],
        "signals": [],
    }
)


def test_select_skills_keeps_profile_backed_terms_in_vacancy_order():
    terminology = normalize_terminology(PROFILE, VACANCY)

    result = select_skills(terminology)

    assert [(skill.category, skill.group, skill.name, skill.canonical) for skill in result.skills] == [
        ("technology", "Architecture & Backend", "Postgres", "postgresql"),
        ("technology", "Architecture & Backend", "Python", "python"),
        ("competency", "Leadership & Delivery", "Technical Leadership", "technical leadership"),
    ]


def test_select_skills_excludes_vacancy_only_terms():
    vacancy = VACANCY.model_copy(update={"technologies": ("K8s",), "domains": (), "signals": ()})

    result = select_skills(normalize_terminology(PROFILE, vacancy))

    assert result.skills == ()


def test_select_skills_deduplicates_canonical_terms():
    terminology = normalize_terminology(PROFILE, VACANCY)

    result = select_skills(terminology)

    assert [skill.canonical for skill in result.skills].count("postgresql") == 1
