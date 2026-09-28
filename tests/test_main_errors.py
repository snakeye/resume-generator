from pathlib import Path

from resume_generator.__main__ import main
from resume_generator.github import GitHubError


def test_main_reports_github_errors_without_traceback(monkeypatch, capsys):
    monkeypatch.setattr("resume_generator.__main__.find_root", lambda _path: Path("."))

    def fail(_args, root):
        raise GitHubError("GitHub unavailable")

    monkeypatch.setattr(
        "resume_generator.__main__.run_force_command",
        fail,
    )

    assert main(["run", "--force", "6"]) == 1
    assert capsys.readouterr().err == "ERROR: GitHub unavailable\n"
