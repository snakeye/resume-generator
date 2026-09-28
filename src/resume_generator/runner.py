"""Single-process orchestration for GitHub Issue resume requests."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .github import GitHubClient, GitHubError, Issue, RepositoryInfo
from .issue import IssueFormError, ResumeTask, format_issue_title, parse_issue_body
from .pipeline import PipelineResult
from .profile import ProfileError, load_profile

Progress = Callable[[str], None]


class RunnerError(RuntimeError):
    """Raised when the runner cannot safely continue processing the queue."""


class Pipeline(Protocol):
    def run(self, task: ResumeTask) -> PipelineResult: ...


class Publisher(Protocol):
    def prepare(self, task: ResumeTask, repository: RepositoryInfo, *, regenerate: bool = False) -> None: ...

    def publish(self, task: ResumeTask, result: PipelineResult, repository: RepositoryInfo) -> object: ...

    def restore_default_branch(self, repository: RepositoryInfo) -> None: ...


@dataclass(frozen=True)
class RunnerConfig:
    root: Path
    poll_interval: float = 60.0

    @property
    def lock_path(self) -> Path:
        return self.root / "data" / ".runner.lock"


@contextmanager
def process_lock(path: Path) -> Iterator[None]:
    """Acquire an exclusive local lock without deleting another process's lock."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise RunnerError(f"Another runner is already active: {path}") from error
    try:
        os.write(descriptor, f"{os.getpid()}\n".encode())
        yield
    finally:
        os.close(descriptor)
        path.unlink(missing_ok=True)


def run_once(
    github: GitHubClient,
    pipeline: Pipeline,
    config: RunnerConfig,
    *,
    publisher: Publisher | None = None,
    git_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    progress: Progress | None = None,
) -> bool:
    """Reconcile interrupted work and process one ready issue, if available."""
    with process_lock(config.lock_path):
        repository = _verify_repository(github, config.root, git_runner)
        _reconcile_working(github)
        issues = [(issue, False) for issue in github.ready_issues()]
        issues.extend((issue, True) for issue in github.regeneration_issues())
        if not issues:
            return False
        issue, regenerate = min(issues, key=lambda item: (item[0].created_at, item[0].number))
        process_task(
            issue,
            github,
            pipeline,
            config,
            repository=repository,
            publisher=publisher,
            regenerate=regenerate,
            progress=progress,
        )
        return True


def run_forced(
    issue_number: int,
    github: GitHubClient,
    pipeline: Pipeline,
    config: RunnerConfig,
    *,
    publisher: Publisher | None = None,
    git_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    progress: Progress | None = None,
) -> PipelineResult:
    """Process one explicitly requested issue, regardless of its lifecycle label."""
    with process_lock(config.lock_path):
        repository = _verify_repository(github, config.root, git_runner)
        _reconcile_working(github)
        issue = github.issue(issue_number)
        return process_task(
            issue,
            github,
            pipeline,
            config,
            repository=repository,
            publisher=publisher,
            regenerate=True,
            progress=progress,
        )


def run_forever(
    github: GitHubClient,
    pipeline: Pipeline,
    config: RunnerConfig,
    *,
    publisher: Publisher | None = None,
    sleep: Callable[[float], None] = time.sleep,
    git_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    progress: Progress | None = None,
) -> None:
    """Poll until interrupted, finishing the current safe operation first."""
    stopping = False

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    previous = {signum: signal.getsignal(signum) for signum in (signal.SIGINT, signal.SIGTERM)}
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        while not stopping:
            run_once(github, pipeline, config, publisher=publisher, git_runner=git_runner, progress=progress)
            if not stopping:
                sleep(config.poll_interval)
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def process_task(
    issue: Issue,
    github: GitHubClient,
    pipeline: Pipeline,
    config: RunnerConfig,
    *,
    repository: RepositoryInfo | None = None,
    publisher: Publisher | None = None,
    regenerate: bool = False,
    progress: Progress | None = None,
) -> PipelineResult:
    """Process one issue and always restore the repository default branch."""
    try:
        return _process_task(
            issue,
            github,
            pipeline,
            config,
            repository=repository,
            publisher=publisher,
            regenerate=regenerate,
            progress=progress,
        )
    finally:
        if publisher is not None and repository is not None:
            publisher.restore_default_branch(repository)


def _process_task(
    issue: Issue,
    github: GitHubClient,
    pipeline: Pipeline,
    config: RunnerConfig,
    *,
    repository: RepositoryInfo | None = None,
    publisher: Publisher | None = None,
    regenerate: bool = False,
    progress: Progress | None = None,
) -> PipelineResult:
    """Claim, validate, execute, and optionally publish one issue."""
    _claim_issue(github, issue.number, regenerate)
    github.comment(issue.number, "Resume generation started.")
    _report(progress, f"Processing issue #{issue.number}")
    try:
        task = parse_issue_body(
            issue.body,
            issue_number=issue.number,
            issue_created_at=issue.created_at,
        )
        github.edit_title(issue.number, format_issue_title(task.company, task.position, issue.created_at))
        load_profile(config.root / "data/profile/profile.yaml")
        if publisher is not None:
            if repository is None:
                raise RunnerError("Repository metadata is required before publishing.")
            publisher.prepare(task, repository, regenerate=regenerate)
            _report(progress, "Publishing preparation complete")
        _report(progress, "Starting resume generation")
        result = pipeline.run(task)
    except (IssueFormError, ProfileError, GitHubError, RunnerError, OSError) as error:
        _fail_issue(github, issue.number, str(error))
        raise RunnerError(str(error)) from error
    except Exception as error:  # noqa: BLE001 - pipeline failures cross the runner boundary
        _fail_issue(github, issue.number, str(error))
        raise RunnerError(str(error)) from error

    if not result.success:
        _report(progress, f"Resume generation failed: {result.error or 'unknown error'}")
        _fail_issue(github, issue.number, result.error or "Pipeline failed without a reason.")
        return result

    if publisher is not None:
        if repository is None:
            raise RunnerError("Repository metadata is required before publishing.")
        pull_request = publisher.publish(task, result, repository)
        _report(progress, f"Published pull request #{pull_request.number}")
        github.set_lifecycle(issue.number, "resume:review")
        github.comment(issue.number, f"Resume generated successfully.\n\nPull request: #{pull_request.number}")
        return result

    github.comment(
        issue.number,
        "Resume pipeline completed locally. Publishing is not enabled yet; the request remains in working state.",
    )
    _report(progress, f"Run completed. Artifacts: {result.output_directory}")
    return result


def _report(progress: Progress | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _claim_issue(github: GitHubClient, issue_number: int, regenerate: bool) -> None:
    if regenerate:
        github.claim_regeneration(issue_number)
        return
    github.set_lifecycle(issue_number, "resume:working")


def _verify_repository(
    github: GitHubClient,
    root: Path,
    git_runner: Callable[..., subprocess.CompletedProcess[str]],
) -> RepositoryInfo:
    try:
        repository = github.repository()
        result = git_runner(["git", "status", "--porcelain"], cwd=root, check=False, capture_output=True, text=True)
    except (GitHubError, OSError) as error:
        raise RunnerError(f"Cannot verify repository before polling: {error}") from error
    if result.returncode != 0:
        raise RunnerError("Cannot inspect repository cleanliness before polling.")
    if result.stdout.strip():
        raise RunnerError("Runner paused: repository contains local changes.")
    if not repository.is_private:
        raise RunnerError("The repository is public. Use a private repository before running the queue.")
    return repository


def _reconcile_working(github: GitHubClient) -> None:
    for issue in github.working_issues():
        branch = f"resume/{issue.number}"
        if github.pull_requests_for_branch(branch):
            github.set_lifecycle(issue.number, "resume:review")
            continue
        github.set_lifecycle(issue.number, "resume:ready")
        github.comment(issue.number, "Previous processing was interrupted. The task has been returned to the queue.")


def _fail_issue(github: GitHubClient, issue_number: int, reason: str) -> None:
    github.set_lifecycle(issue_number, "resume:failed")
    safe_reason = " ".join(reason.split())[:500] or "Unknown failure."
    github.comment(issue_number, f"Resume generation failed.\n\nReason: {safe_reason}")
