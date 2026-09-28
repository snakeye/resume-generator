from pathlib import Path

from resume_generator.assembly import assemble_resume
from resume_generator.headline import Headline
from resume_generator.profile import EarlierExperiencePreferences, load_profile
from resume_generator.skills import SkillsSelection
from resume_generator.validation import validate_resume
from resume_generator.voice import VoiceAdaptation

PROFILE = load_profile(Path("data/examples/profile/profile.example.yaml"))


def make_resume(*, headline: str = "Senior Backend Engineer", summary: str = "Python engineer."):
    return assemble_resume(
        PROFILE,
        Headline.model_validate({"schema_version": 1, "text": headline, "fact_paths": ["work[0].facts[0]"]}),
        VoiceAdaptation.model_validate(
            {
                "schema_version": 1,
                "summary": {"text": summary, "fact_paths": ["work[0].facts[0]"]},
                "bullets": [
                    {"text": "Reduced API latency by 35%.", "fact_paths": ["work[0].facts[0]"]},
                ],
            }
        ),
        SkillsSelection.model_validate(
            {
                "schema_version": 2,
                "skills": (
                    {
                        "category": "technology",
                        "group": "Architecture & Backend",
                        "name": "Python",
                        "canonical": "python",
                    },
                ),
            }
        ),
    )


def test_validation_accepts_profile_supported_resume():
    report = validate_resume(PROFILE, make_resume())

    assert report.valid is True
    assert report.issues == ()


def test_validation_rejects_unsupported_number():
    report = validate_resume(PROFILE, make_resume(summary="Improved delivery by 99%."))

    assert report.valid is False
    assert report.issues[0].code == "claim.unsupported_number"


def test_validation_warns_for_uncovered_must_have():
    from resume_generator.vacancy import VacancyAnalysis

    vacancy = VacancyAnalysis.model_validate(
        {
            "schema_version": 1,
            "role": "Engineer",
            "requirements": [{"id": "req-01", "text": "Kubernetes", "priority": "must_have"}],
            "responsibilities": [],
            "technologies": [],
            "domains": [],
            "signals": [],
        }
    )

    report = validate_resume(PROFILE, make_resume(), vacancy=vacancy)

    assert report.valid is True
    assert report.issues[0].code == "coverage.uncovered"


def test_validation_accepts_source_backed_earlier_experience():
    profile = PROFILE.model_copy(
        update={
            "preferences": PROFILE.preferences.model_copy(
                update={"earlier_experience": EarlierExperiencePreferences(detailed_positions=1)}
            )
        }
    )
    resume = assemble_resume(
        profile,
        Headline.model_validate({"schema_version": 1, "text": "Engineer", "fact_paths": ["work[0].facts[0]"]}),
        VoiceAdaptation.model_validate(
            {
                "schema_version": 1,
                "summary": {"text": "Engineer.", "fact_paths": ["work[0].facts[0]"]},
                "bullets": [{"text": "Built systems.", "fact_paths": ["work[1].facts[0]"]}],
            }
        ),
        SkillsSelection.model_validate({"schema_version": 2, "skills": ()}),
    )

    assert validate_resume(profile, resume).valid is True
