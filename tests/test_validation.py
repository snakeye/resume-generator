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


def test_validation_rejects_spelled_out_unsupported_quantity():
    report = validate_resume(PROFILE, make_resume(summary="Managed twelve teams."))

    assert report.valid is False
    assert report.issues[0].code == "claim.unsupported_number"


def test_validation_rejects_semantically_stronger_responsibility():
    report = validate_resume(PROFILE, make_resume(summary="Owned platform strategy."))

    assert report.valid is False
    issue = next(issue for issue in report.issues if issue.code == "claim.semantic_drift")
    assert issue.claim == "Owned platform strategy."
    assert issue.evidence == (PROFILE.work[0].facts[0].text,)


def test_validation_rejects_led_when_profile_only_supports_contribution():
    report = validate_resume(PROFILE, make_resume(summary="Led the database redesign."))

    assert report.valid is False
    assert any(issue.code == "claim.semantic_drift" for issue in report.issues)


def test_validation_rejects_stronger_seniority_claim():
    report = validate_resume(PROFILE, make_resume(summary="Principal engineer focused on APIs."))

    assert report.valid is False
    assert any(issue.code == "claim.seniority_drift" for issue in report.issues)


def test_validation_rejects_unsupported_technology():
    report = validate_resume(PROFILE, make_resume(summary="Built Kubernetes platforms."))

    assert report.valid is False
    assert any(issue.code == "claim.unsupported_technology" for issue in report.issues)


def test_validation_rejects_changed_education():
    resume = make_resume().model_copy(
        update={"education": (make_resume().education[0].model_copy(update={"institution": "Other University"}),)}
    )

    report = validate_resume(PROFILE, resume)

    assert report.valid is False
    assert any(issue.code == "immutable.education" for issue in report.issues)


def test_validation_rejects_changed_language():
    resume = make_resume().model_copy(
        update={
            "languages": (
                make_resume().languages[0].model_copy(update={"level": "Native"}),
                *make_resume().languages[1:],
            )
        }
    )

    report = validate_resume(PROFILE, resume)

    assert report.valid is False
    assert any(issue.code == "immutable.language" for issue in report.issues)


def test_validation_rejects_changed_company():
    resume = make_resume()
    resume = resume.model_copy(
        update={
            "experience": (
                resume.experience[0].model_copy(update={"company": "Other Company"}),
                *resume.experience[1:],
            )
        }
    )

    report = validate_resume(PROFILE, resume)

    assert report.valid is False
    assert any(issue.code == "immutable.work_field" for issue in report.issues)


def test_validation_rejects_changed_role_date():
    resume = make_resume()
    company = resume.experience[0]
    role = company.roles[0].model_copy(update={"start_date": "2020-01"})
    resume = resume.model_copy(
        update={"experience": (company.model_copy(update={"roles": (role,)}), *resume.experience[1:])}
    )

    report = validate_resume(PROFILE, resume)

    assert report.valid is False
    assert any(issue.code == "immutable.work_field" for issue in report.issues)


def test_validation_reports_team_attribution_as_blocking():
    resume = make_resume(summary="I delivered the team result.").model_copy(
        update={
            "summary": make_resume().summary.model_copy(
                update={"text": "I delivered the team result.", "fact_paths": ("work[0].facts[1]",)}
            )
        }
    )

    report = validate_resume(PROFILE, resume)

    assert report.valid is False
    assert any(issue.code == "claim.team_attribution" for issue in report.issues)


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
