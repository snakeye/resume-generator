import subprocess

import pytest

import resume_generator.runner as runner_module
from resume_generator.github import Issue, PullRequest, RepositoryInfo
from resume_generator.pipeline import PipelineResult
from resume_generator.runner import RunnerConfig, RunnerError, process_lock, run_forced, run_once

VALID_BODY = """### Company

Example GmbH

### Position

Engineer

### Resume language

English

### Job description

Build reliable systems.

### Additional preferences


### Form version

1
"""


class FakeGitHub:
    def __init__(self, issues=None, regeneration=None, working=None, prs=None):
        self.issues = issues or []
        self.regeneration = regeneration or []
        self.working = working or []
        self.prs = prs or {}
        self.transitions = []
        self.comments = []
        self.titles = []

    def repository(self):
        return RepositoryInfo("example/repo", "main", True)

    def ready_issues(self):
        return self.issues

    def regeneration_issues(self):
        return self.regeneration

    def working_issues(self):
        return self.working

    def pull_requests_for_branch(self, branch):
        return self.prs.get(branch, [])

    def set_lifecycle(self, issue_number, label):
        self.transitions.append((issue_number, label))

    def claim_regeneration(self, issue_number):
        self.transitions.append((issue_number, "resume:working"))

    def comment(self, issue_number, body):
        self.comments.append((issue_number, body))

    def edit_title(self, issue_number, title):
        self.titles.append((issue_number, title))


class FakePipeline:
    def __init__(self, result):
        self.result = result
        self.tasks = []

    def run(self, task):
        self.tasks.append(task)
        return self.result


class FakePublisher:
    def __init__(self):
        self.prepared = []
        self.published = []
        self.restored = []
        self.recovered = []

    def recover(self, task, repository, pull_requests):
        self.recovered.append((task, repository, pull_requests))

    def prepare(self, task, repository, *, regenerate=False):
        self.prepared.append((task, repository, regenerate))

    def publish(self, task, result, repository):
        self.published.append((task, result, repository))
        return PullRequest(99)

    def restore_default_branch(self, repository):
        self.restored.append(repository.default_branch)


def clean_git_runner(*_args, **_kwargs):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")


def issue(number=42):
    return Issue(number, VALID_BODY, "2026-01-01T00:00:00Z")


def test_run_once_processes_oldest_ready_issue(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_module, "load_profile", lambda _path: object())
    github = FakeGitHub(issues=[issue()])
    pipeline = FakePipeline(PipelineResult(success=True, output_directory=tmp_path / "run"))

    processed = run_once(github, pipeline, RunnerConfig(tmp_path), git_runner=clean_git_runner)

    assert processed is True
    assert pipeline.tasks[0].issue_number == 42
    assert pipeline.tasks[0].issue_created_at == "2026-01-01T00:00:00Z"
    assert github.titles == [(42, "[Resume] Example GmbH — Engineer — 2026-01-01")]
    assert github.transitions == [(42, "resume:working")]
    assert any("completed locally" in body for _, body in github.comments)


def test_run_forced_processes_requested_issue_without_queue_labels(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_module, "load_profile", lambda _path: object())
    github = FakeGitHub()
    github.issue = lambda number: issue(number)
    pipeline = FakePipeline(PipelineResult(success=True, output_directory=tmp_path / "run"))
    publisher = FakePublisher()

    result = run_forced(
        6,
        github,
        pipeline,
        RunnerConfig(tmp_path),
        publisher=publisher,
        git_runner=clean_git_runner,
    )

    assert result.success is True
    assert [task.issue_number for task in pipeline.tasks] == [6]
    assert github.transitions == [(6, "resume:working"), (6, "resume:review")]
    assert publisher.prepared[0][2] is True


def test_pipeline_failure_marks_issue_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_module, "load_profile", lambda _path: object())
    github = FakeGitHub(issues=[issue()])
    pipeline = FakePipeline(
        PipelineResult(success=False, output_directory=tmp_path / "run", error="provider unavailable")
    )

    run_once(github, pipeline, RunnerConfig(tmp_path), git_runner=clean_git_runner)

    assert github.transitions == [(42, "resume:working"), (42, "resume:failed")]
    assert any("provider unavailable" in body for _, body in github.comments)


def test_successful_publishing_moves_issue_to_review(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_module, "load_profile", lambda _path: object())
    github = FakeGitHub(issues=[issue()])
    pipeline = FakePipeline(PipelineResult(success=True, output_directory=tmp_path / "run"))
    publisher = FakePublisher()

    run_once(
        github,
        pipeline,
        RunnerConfig(tmp_path),
        publisher=publisher,
        git_runner=clean_git_runner,
    )

    assert github.transitions == [(42, "resume:working"), (42, "resume:review")]
    assert publisher.prepared[0][1].default_branch == "main"
    assert publisher.published[0][0].issue_number == 42
    assert publisher.restored == ["main"]
    assert any("Pull request: #99" in body for _, body in github.comments)


def test_regeneration_updates_existing_review_request(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_module, "load_profile", lambda _path: object())
    github = FakeGitHub(regeneration=[issue()])
    pipeline = FakePipeline(PipelineResult(success=True, output_directory=tmp_path / "run"))
    publisher = FakePublisher()

    run_once(
        github,
        pipeline,
        RunnerConfig(tmp_path),
        publisher=publisher,
        git_runner=clean_git_runner,
    )

    assert github.transitions == [(42, "resume:working"), (42, "resume:review")]
    assert publisher.prepared[0][2] is True


def test_failed_issue_with_regenerate_label_updates_existing_request(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_module, "load_profile", lambda _path: object())
    github = FakeGitHub(regeneration=[issue()])
    pipeline = FakePipeline(PipelineResult(success=True, output_directory=tmp_path / "run"))
    publisher = FakePublisher()

    run_once(
        github,
        pipeline,
        RunnerConfig(tmp_path),
        publisher=publisher,
        git_runner=clean_git_runner,
    )

    assert github.transitions == [(42, "resume:working"), (42, "resume:review")]
    assert publisher.prepared[0][2] is True


def test_failed_pipeline_restores_default_branch(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_module, "load_profile", lambda _path: object())
    github = FakeGitHub(issues=[issue()])
    publisher = FakePublisher()

    run_once(
        github,
        FakePipeline(PipelineResult(success=False, output_directory=tmp_path, error="selection failed")),
        RunnerConfig(tmp_path),
        publisher=publisher,
        git_runner=clean_git_runner,
    )

    assert publisher.restored == ["main"]


def test_working_issue_with_no_pr_returns_to_ready(tmp_path):
    interrupted = issue(7)
    github = FakeGitHub(working=[interrupted])

    assert (
        run_once(
            github,
            FakePipeline(PipelineResult(success=True, output_directory=tmp_path)),
            RunnerConfig(tmp_path),
            git_runner=clean_git_runner,
        )
        is False
    )

    assert github.transitions == [(7, "resume:ready")]
    assert any("returned to the queue" in body for _, body in github.comments)


def test_working_issue_with_pr_moves_to_review(tmp_path):
    interrupted = issue(7)
    github = FakeGitHub(working=[interrupted], prs={"resume/7": [PullRequest(8)]})

    run_once(
        github,
        FakePipeline(PipelineResult(success=True, output_directory=tmp_path)),
        RunnerConfig(tmp_path),
        git_runner=clean_git_runner,
    )

    assert github.transitions == [(7, "resume:review")]


def test_multiple_working_issues_are_reconciled_before_polling(tmp_path):
    github = FakeGitHub(working=[issue(7), issue(8)])

    assert (
        run_once(
            github,
            FakePipeline(PipelineResult(success=True, output_directory=tmp_path)),
            RunnerConfig(tmp_path),
            git_runner=clean_git_runner,
        )
        is False
    )

    assert github.transitions == [(7, "resume:ready"), (8, "resume:ready")]


def test_multiple_open_pull_requests_stop_recovery(tmp_path):
    github = FakeGitHub(working=[issue(7)], prs={"resume/7": [PullRequest(8), PullRequest(9)]})

    with pytest.raises(RunnerError, match="multiple open Pull Requests"):
        run_once(
            github,
            FakePipeline(PipelineResult(success=True, output_directory=tmp_path)),
            RunnerConfig(tmp_path),
            git_runner=clean_git_runner,
        )

    assert github.transitions == []


def test_publishing_failure_keeps_issue_recoverable(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_module, "load_profile", lambda _path: object())
    github = FakeGitHub(issues=[issue()])
    publisher = FakePublisher()

    def fail_publish(*_args, **_kwargs):
        from resume_generator.publishing import PublishingError

        raise PublishingError("push failed")

    publisher.publish = fail_publish

    result = run_once(
        github,
        FakePipeline(PipelineResult(success=True, output_directory=tmp_path)),
        RunnerConfig(tmp_path),
        publisher=publisher,
        git_runner=clean_git_runner,
    )

    assert result is True
    assert github.transitions == [(42, "resume:working")]


def test_github_failure_after_publish_keeps_issue_recoverable(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_module, "load_profile", lambda _path: object())

    class FailingGitHub(FakeGitHub):
        def set_lifecycle(self, issue_number, label):
            if label == "resume:review":
                from resume_generator.github import GitHubError

                raise GitHubError("GitHub unavailable")
            super().set_lifecycle(issue_number, label)

    github = FailingGitHub(issues=[issue()])
    publisher = FakePublisher()

    result = run_once(
        github,
        FakePipeline(PipelineResult(success=True, output_directory=tmp_path)),
        RunnerConfig(tmp_path),
        publisher=publisher,
        git_runner=clean_git_runner,
    )

    assert result is True
    assert github.transitions == [(42, "resume:working")]


def test_dirty_repository_stops_before_claiming_issue(tmp_path):
    github = FakeGitHub(issues=[issue()])

    def dirty_git_runner(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=" M data/profile/profile.yaml\n", stderr="")

    with pytest.raises(RunnerError, match="local changes"):
        run_once(
            github,
            FakePipeline(PipelineResult(success=True, output_directory=tmp_path)),
            RunnerConfig(tmp_path),
            git_runner=dirty_git_runner,
        )

    assert github.transitions == []


def test_process_lock_rejects_second_owner(tmp_path):
    path = tmp_path / "data/.runner.lock"
    with process_lock(path), pytest.raises(RunnerError, match="already active"), process_lock(path):
        pass

    assert not path.exists()
