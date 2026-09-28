from pathlib import Path

import pytest

from resume_generator.profile import ProfileError, load_profile

EXAMPLE = Path("data/examples/profile/profile.example.yaml")


def test_example_profile_loads_into_normalized_values():
    profile = load_profile(EXAMPLE)

    assert profile.work[0].skills == ("Python", "PostgreSQL", "Technical Leadership", "System Design")
    assert [group.name for group in profile.skill_groups] == [
        "Leadership & Delivery",
        "Architecture & Backend",
        "Platform, Data & Reliability",
    ]
    assert profile.work[0].facts[0].text.startswith("Reduced API response time")
    assert len(profile.aliases) > 50
    assert profile.preferences.minimum_experience_bullets == 3
    assert profile.voice.concise is True
    assert profile.voice.language_background == (
        "Native synthetic-language speaker with strong English; write in clear, direct professional English"
    )


def test_example_profile_files_use_yaml_not_json_syntax():
    for name in ("profile", "preferences", "voice", "aliases"):
        content = (EXAMPLE.parent / f"{name}.example.yaml").read_text(encoding="utf-8")
        assert not content.lstrip().startswith("{")


def test_voice_language_background_is_loaded(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(
        """schema_version: 1
basics: {name: Alex, email: alex@example.com}
work:
  - company: Example
    position: Engineer
    start_date: 2024-01
    facts: [Built systems]
""",
        encoding="utf-8",
    )
    (tmp_path / "voice.yaml").write_text(
        "language_background: Native German speaker with strong English\n", encoding="utf-8"
    )

    profile = load_profile(path)

    assert profile.voice.language_background == "Native German speaker with strong English"


def test_minimum_experience_bullets_defaults_to_three(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(
        """schema_version: 1
basics: {name: Alex, email: alex@example.com}
work:
  - company: Example
    position: Engineer
    start_date: 2024-01
    facts: [Built systems]
""",
        encoding="utf-8",
    )

    profile = load_profile(path)

    assert profile.preferences.minimum_experience_bullets == 3


def test_minimum_experience_bullets_must_be_positive(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(
        """schema_version: 1
basics: {name: Alex, email: alex@example.com}
work:
  - company: Example
    position: Engineer
    start_date: 2024-01
    facts: [Built systems]
""",
        encoding="utf-8",
    )
    (tmp_path / "preferences.yaml").write_text("minimum_experience_bullets: 0\n", encoding="utf-8")

    with pytest.raises(ProfileError, match="minimum_experience_bullets.*greater than or equal to 1"):
        load_profile(path)


def test_earlier_experience_can_group_by_detailed_position_count(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(
        """schema_version: 1
basics: {name: Alex, email: alex@example.com}
work:
  - {company: Recent, position: Engineer, start_date: 2024-01, facts: [Built systems]}
  - {company: Earlier, position: Engineer, start_date: 2020-01, end_date: 2023-12, facts: [Built more systems]}
""",
        encoding="utf-8",
    )
    (tmp_path / "preferences.yaml").write_text("earlier_experience:\n  detailed_positions: 1\n", encoding="utf-8")

    profile = load_profile(path)

    assert profile.preferences.earlier_experience.detailed_positions == 1


def test_earlier_experience_selectors_are_mutually_exclusive(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(
        """schema_version: 1
basics: {name: Alex, email: alex@example.com}
work:
  - {company: Recent, position: Engineer, start_date: 2024-01, facts: [Built systems]}
""",
        encoding="utf-8",
    )
    (tmp_path / "preferences.yaml").write_text(
        "earlier_experience:\n  detailed_positions: 1\n  ending_before: 2024-01\n", encoding="utf-8"
    )

    with pytest.raises(ProfileError, match="only one of detailed_positions or ending_before"):
        load_profile(path)


def test_blank_voice_language_background_is_rejected(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(
        """schema_version: 1
basics: {name: Alex, email: alex@example.com}
work:
  - company: Example
    position: Engineer
    start_date: 2024-01
    facts: [Built systems]
""",
        encoding="utf-8",
    )
    (tmp_path / "voice.yaml").write_text("language_background: '   '\n", encoding="utf-8")

    with pytest.raises(ProfileError, match="must not be blank"):
        load_profile(path)


def test_unknown_profile_field_is_rejected(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text("schema_version: 1\nbasics: {}\nwork: []\nunexpected: true\n", encoding="utf-8")

    with pytest.raises(ProfileError, match="unknown field 'unexpected'"):
        load_profile(path)


def test_fact_must_be_a_string(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(
        """
schema_version: 1
basics: {name: Alex, email: alex@example.com}
work:
  - company: Example
    position: Engineer
    start_date: 2024-01
    facts:
      - {text: Built systems}
  - company: Example 2
    position: Engineer
    start_date: 2023-01
    facts:
      - {text: Built more systems}
""",
        encoding="utf-8",
    )

    with pytest.raises(ProfileError, match=r"work\[0\]\.facts\[0\].*non-empty string"):
        load_profile(path)


def test_invalid_date_is_rejected(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(
        """
schema_version: 1
basics: {name: Alex, email: alex@example.com}
work:
  - company: Example
    position: Engineer
    start_date: 2024-13
    facts:
      - Built systems
""",
        encoding="utf-8",
    )

    with pytest.raises(ProfileError, match="month from 01 to 12"):
        load_profile(path)


def test_profile_file_is_not_rewritten(tmp_path):
    path = tmp_path / "profile.yaml"
    original = EXAMPLE.read_text(encoding="utf-8")
    path.write_text(original, encoding="utf-8")

    load_profile(path)

    assert path.read_text(encoding="utf-8") == original
