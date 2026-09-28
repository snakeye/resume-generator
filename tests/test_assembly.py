from pathlib import Path

import pytest

from resume_generator.assembly import ResumeAssemblyError, assemble_resume
from resume_generator.experience import experience_groups
from resume_generator.headline import Headline
from resume_generator.profile import EarlierExperiencePreferences, load_profile
from resume_generator.skills import SkillsSelection
from resume_generator.voice import AdaptedText, VoiceAdaptation

PROFILE = load_profile(Path("data/examples/profile/profile.example.yaml"))
HEADLINE = Headline.model_validate(
    {"schema_version": 1, "text": "Senior Backend Engineer", "fact_paths": ["work[0].facts[0]"]}
)
VOICE = VoiceAdaptation.model_validate(
    {
        "schema_version": 1,
        "summary": {"text": "Python engineer.", "fact_paths": ["work[0].facts[0]"]},
        "bullets": [
            {"text": "Reduced API latency.", "fact_paths": ["work[0].facts[0]"]},
            {"text": "Built event-driven services.", "fact_paths": ["work[1].facts[0]"]},
        ],
    }
)
SKILLS = SkillsSelection.model_validate(
    {
        "schema_version": 2,
        "skills": (
            {"category": "technology", "group": "Architecture & Backend", "name": "Python", "canonical": "python"},
        ),
    }
)


def test_assemble_resume_preserves_profile_fields_and_work_order():
    result = assemble_resume(PROFILE, HEADLINE, VOICE, SKILLS)

    assert result.basics == PROFILE.basics
    assert [(company.company, role.position) for company in result.experience for role in company.roles] == [
        (work.company, work.position) for work in PROFILE.work
    ]
    assert result.experience[0].roles[0].bullets[0].text == "Reduced API latency."
    assert result.experience[1].roles[0].bullets[0].text == "Built event-driven services."
    assert result.education[0].degree_line == "Bachelor of Science in Computer Science"
    assert result.education[0].details == ("Completed coursework and a capstone project in distributed systems.",)
    assert [(item.language, item.level) for item in result.languages] == [("English", "C1"), ("German", "B2")]


def test_assemble_resume_keeps_positions_without_bullets():
    voice = VoiceAdaptation.model_validate(
        {
            "schema_version": 1,
            "summary": {"text": "Python engineer.", "fact_paths": ["work[0].facts[0]"]},
            "bullets": [{"text": "Reduced API latency.", "fact_paths": ["work[0].facts[0]"]}],
        }
    )

    result = assemble_resume(PROFILE, HEADLINE, voice, SKILLS)

    assert sum(len(company.roles) for company in result.experience) == len(PROFILE.work)
    assert result.experience[1].roles[0].bullets == ()


def test_assemble_resume_rejects_bullet_spanning_positions():
    voice = VoiceAdaptation.model_validate(
        {
            "schema_version": 1,
            "summary": {"text": "Python engineer.", "fact_paths": ["work[0].facts[0]"]},
            "bullets": [
                {
                    "text": "Combined experience.",
                    "fact_paths": ["work[0].facts[0]", "work[1].facts[0]"],
                }
            ],
        }
    )

    with pytest.raises(ResumeAssemblyError, match="multiple work positions"):
        assemble_resume(PROFILE, HEADLINE, voice, SKILLS)


def test_assemble_resume_rejects_invalid_fact_path():
    voice = VoiceAdaptation.model_construct(
        schema_version=1,
        summary=AdaptedText(text="Python engineer.", fact_paths=("work[0].facts[0]",)),
        bullets=(AdaptedText(text="Invalid.", fact_paths=("not-a-path",)),),
    )

    with pytest.raises(ResumeAssemblyError, match="Invalid fact path"):
        assemble_resume(PROFILE, HEADLINE, voice, SKILLS)


def test_assemble_resume_puts_configured_tail_in_earlier_experience():
    profile = PROFILE.model_copy(
        update={
            "preferences": PROFILE.preferences.model_copy(
                update={"earlier_experience": EarlierExperiencePreferences(detailed_positions=1)}
            )
        }
    )

    result = assemble_resume(profile, HEADLINE, VOICE, SKILLS)

    assert len(result.experience) == 1
    assert [(role.company, role.position) for role in result.earlier_experience.source_roles] == [
        (profile.work[1].company, profile.work[1].position)
    ]
    assert result.earlier_experience.source_roles[0].work_path == "work[1]"


def test_ending_before_groups_only_completed_old_positions():
    profile = PROFILE.model_copy(
        update={
            "preferences": PROFILE.preferences.model_copy(
                update={"earlier_experience": EarlierExperiencePreferences(ending_before="2022-01")}
            )
        }
    )

    assert experience_groups(profile)[-1].work_indexes == (1,)
