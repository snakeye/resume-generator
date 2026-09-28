import subprocess

import pytest

from resume_generator.github import PullRequest, RepositoryInfo
from resume_generator.issue import ResumeTask
from resume_generator.pipeline import PipelineResult
from resume_generator.publishing import GitPublisher, PublishingError, branch_name


def task(number=42):
    return ResumeTask(
        form_version=1,
        issue_number=number,
        issue_created_at="2026-01-01T00:00:00Z",
        company="Example GmbH",
        position="Engineer",
        language="English",
        job_description="Build reliable systems.",
    )


class FakeGitHub:
    def __init__(self, pull_requests=None):
        self.pull_requests = pull_requests or []
        self.created = None

    def pull_requests_for_branch(self, _branch):
        return self.pull_requests

    def create_pull_request(self, **values):
        self.created = values
        return PullRequest(99)


def successful_git_runner(calls):
    def runner(arguments, **_kwargs):
        calls.append(arguments)
        return subprocess.CompletedProcess(args=arguments, returncode=0, stdout="", stderr="")

    return runner


def test_branch_name_is_stable():
    assert branch_name(task(17)) == "resume/17"


def test_publisher_uses_exact_artifact_allowlist(tmp_path):
    output = tmp_path / "data/output/2026-01-01/42-example-gmbh-engineer"
    output.mkdir(parents=True)
    for name in (
        "resume.json",
        "resume.md",
        "resume.tex",
        "resume.pdf",
        "resume.docx",
        "report.md",
        "run-metadata.json",
    ):
        (output / name).write_text(name, encoding="utf-8")
    calls = []
    github = FakeGitHub()
    publisher = GitPublisher(root=tmp_path, github=github, runner=successful_git_runner(calls))
    repository = RepositoryInfo("example/repo", "main", True)

    publisher.prepare(task(), repository)
    pull_request = publisher.publish(task(), PipelineResult(success=True, output_directory=output), repository)

    add_call = next(call for call in calls if call[1] == "add")
    assert add_call[3:] == [
        "data/output/2026-01-01/42-example-gmbh-engineer/resume.json",
        "data/output/2026-01-01/42-example-gmbh-engineer/resume.md",
        "data/output/2026-01-01/42-example-gmbh-engineer/resume.tex",
        "data/output/2026-01-01/42-example-gmbh-engineer/resume.pdf",
        "data/output/2026-01-01/42-example-gmbh-engineer/resume.docx",
        "data/output/2026-01-01/42-example-gmbh-engineer/report.md",
        "data/output/2026-01-01/42-example-gmbh-engineer/run-metadata.json",
    ]
    assert pull_request.number == 99
    assert github.created["head"] == "resume/42"
    assert "Closes #42" in github.created["body"]


def test_publisher_rejects_duplicate_open_pull_request(tmp_path):
    github = FakeGitHub([PullRequest(99)])
    publisher = GitPublisher(root=tmp_path, github=github, runner=successful_git_runner([]))

    with pytest.raises(PublishingError, match="already exists"):
        publisher.prepare(task(), RepositoryInfo("example/repo", "main", True))


def test_publisher_updates_existing_pull_request_on_regeneration(tmp_path):
    output = tmp_path / "data/output/2026-01-01/42-example-gmbh-engineer"
    output.mkdir(parents=True)
    for name in (
        "resume.json",
        "resume.md",
        "resume.tex",
        "resume.pdf",
        "resume.docx",
        "report.md",
        "run-metadata.json",
    ):
        (output / name).write_text(name, encoding="utf-8")
    calls = []
    existing = PullRequest(99)
    github = FakeGitHub([existing])
    publisher = GitPublisher(root=tmp_path, github=github, runner=successful_git_runner(calls))
    repository = RepositoryInfo("example/repo", "main", True)

    publisher.prepare(task(), repository, regenerate=True)
    pull_request = publisher.publish(task(), PipelineResult(success=True, output_directory=output), repository)

    assert pull_request == existing
    push_call = next(call for call in calls if call[1] == "push")
    assert push_call[1:3] == ["push", "--force-with-lease"]
    assert calls[-1][1:] == ["switch", "main"]


def test_publisher_returns_to_default_branch_after_publishing(tmp_path):
    output = tmp_path / "data/output/2026-01-01/42-example-gmbh-engineer"
    output.mkdir(parents=True)
    for name in (
        "resume.json",
        "resume.md",
        "resume.tex",
        "resume.pdf",
        "resume.docx",
        "report.md",
        "run-metadata.json",
    ):
        (output / name).write_text(name, encoding="utf-8")
    calls = []
    publisher = GitPublisher(root=tmp_path, github=FakeGitHub(), runner=successful_git_runner(calls))
    repository = RepositoryInfo("example/repo", "master", True)

    publisher.prepare(task(), repository)
    publisher.publish(task(), PipelineResult(success=True, output_directory=output), repository)

    assert calls[-1][1:] == ["switch", "master"]
