import json
import subprocess
from pathlib import Path

import pytest

from resume_generator.github import discover_repository
from resume_generator.setup import SetupError, enable_profile_git, setup_repository


def completed(stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["gh"], returncode=0, stdout=stdout, stderr="")


def fake_gh(repository_private: bool = True):
    calls = []

    def runner(arguments, **kwargs):
        calls.append(arguments)
        if arguments[1:3] == ["repo", "view"]:
            return completed(
                json.dumps(
                    {
                        "nameWithOwner": "example/resume",
                        "defaultBranchRef": {"name": "main"},
                        "isPrivate": repository_private,
                    }
                )
            )
        return completed()

    return runner, calls


def test_discover_repository_reads_default_branch():
    runner, _ = fake_gh()

    repository = discover_repository(cwd=Path.cwd(), runner=runner)

    assert repository.name_with_owner == "example/resume"
    assert repository.default_branch == "main"
    assert repository.is_private is True


def test_setup_creates_profile_and_env_once(tmp_path, monkeypatch):
    example = tmp_path / "data/examples/profile/profile.example.yaml"
    example.parent.mkdir(parents=True)
    example.write_text("schema_version: 1\n", encoding="utf-8")
    for name in ("voice.example.yaml", "preferences.example.yaml", "aliases.example.yaml"):
        (example.parent / name).write_text(f"{name}\n", encoding="utf-8")
    runner, calls = fake_gh()
    monkeypatch.setattr("resume_generator.setup.check_local_tools", lambda: [])

    first = setup_repository(root=tmp_path, runner=runner, api_key_reader=lambda: "secret")
    profile = tmp_path / "data/profile/profile.yaml"
    env = tmp_path / ".env"
    profile.write_text("user profile\n", encoding="utf-8")
    env.write_text("DEEPSEEK_API_KEY=keep-me\n", encoding="utf-8")

    second = setup_repository(root=tmp_path, runner=runner, api_key_reader=lambda: "different")

    assert "Created data/profile/profile.yaml" in first
    assert all(
        (tmp_path / "data/profile" / name).exists() for name in ("voice.yaml", "preferences.yaml", "aliases.yaml")
    )
    assert "Created .env" in first
    assert "Profile already exists; left unchanged" in second
    assert profile.read_text(encoding="utf-8") == "user profile\n"
    assert env.read_text(encoding="utf-8") == "DEEPSEEK_API_KEY=keep-me\n"
    assert sum(arguments[1:3] == ["label", "create"] for arguments in calls) == 10


def test_setup_rejects_public_repository(tmp_path, monkeypatch):
    example = tmp_path / "data/examples/profile/profile.example.yaml"
    example.parent.mkdir(parents=True)
    example.write_text("schema_version: 1\n", encoding="utf-8")
    runner, _ = fake_gh(repository_private=False)
    monkeypatch.setattr("resume_generator.setup.check_local_tools", lambda: [])

    with pytest.raises(SetupError, match="repository is public"):
        setup_repository(root=tmp_path, runner=runner, api_key_reader=lambda: "secret")

    assert not (tmp_path / "data/profile/profile.yaml").exists()
    assert not (tmp_path / ".env").exists()


def test_enable_profile_git_requires_explicit_confirmation(tmp_path):
    with pytest.raises(SetupError, match="--confirm"):
        enable_profile_git(root=tmp_path, runner=lambda *_args, **_kwargs: completed(), confirmed=False)


def test_enable_profile_git_rejects_public_repository_without_changes(tmp_path):
    profile = tmp_path / "data/profile/profile.yaml"
    profile.parent.mkdir(parents=True)
    profile.write_text("real profile\n", encoding="utf-8")
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("data/profile/*\n!data/profile/README.md\n", encoding="utf-8")
    runner, _ = fake_gh(repository_private=False)

    with pytest.raises(SetupError, match="repository is public"):
        enable_profile_git(root=tmp_path, runner=runner, confirmed=True)

    assert gitignore.read_text(encoding="utf-8") == "data/profile/*\n!data/profile/README.md\n"


def test_enable_profile_git_requires_valid_profile(tmp_path):
    profile = tmp_path / "data/profile/profile.yaml"
    profile.parent.mkdir(parents=True)
    profile.write_text("schema_version: 1\n", encoding="utf-8")
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("data/profile/*\n!data/profile/README.md\n", encoding="utf-8")
    runner, _ = fake_gh()

    with pytest.raises(ValueError, match="basics"):
        enable_profile_git(root=tmp_path, runner=runner, confirmed=True)

    assert "!data/profile/profile.yaml" not in gitignore.read_text(encoding="utf-8")


def test_enable_profile_git_is_idempotent(tmp_path):
    profile = tmp_path / "data/profile/profile.yaml"
    profile.parent.mkdir(parents=True)
    profile.write_text(Path("data/examples/profile/profile.example.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("data/profile/*\n!data/profile/README.md\n", encoding="utf-8")
    runner, _ = fake_gh()

    first = enable_profile_git(root=tmp_path, runner=runner, confirmed=True)
    second = enable_profile_git(root=tmp_path, runner=runner, confirmed=True)

    assert "Enabled private Git profile mode in .gitignore" in first
    assert "already enabled" in second[0]
    content = gitignore.read_text(encoding="utf-8")
    assert content.count("!data/profile/profile.yaml") == 1
    assert "!data/profile/voice.yaml" in content
    assert "!data/profile/preferences.yaml" in content
    assert "!data/profile/aliases.yaml" in content
    assert "git add" in first[-1]
