"""Git and Pull Request publishing for validated resume artifacts."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from .generation import PUBLISHABLE_FILES, publishable_output_directory
from .github import GitHubClient, PullRequest, RepositoryInfo
from .issue import ResumeTask
from .pipeline import PipelineResult


class PublishingError(RuntimeError):
    """Raised when validated artifacts cannot be published safely."""


GitRunner = Callable[..., subprocess.CompletedProcess[str]]


class GitPublisher:
    """Prepare one issue branch and publish its exact artifact allowlist."""

    def __init__(self, *, root: Path, github: GitHubClient, runner: GitRunner = subprocess.run) -> None:
        self.root = root
        self.github = github
        self.runner = runner
        self._existing_pull_request: PullRequest | None = None

    def prepare(self, task: ResumeTask, repository: RepositoryInfo, *, regenerate: bool = False) -> None:
        branch = branch_name(task)
        self._existing_pull_request = None
        existing = self.github.pull_requests_for_branch(branch)
        if existing and not regenerate:
            raise PublishingError(f"An open Pull Request already exists for {branch}.")
        if regenerate:
            if len(existing) != 1:
                raise PublishingError(f"Cannot regenerate {branch}; expected exactly one open Pull Request.")
            self._existing_pull_request = existing[0]
        _git(self.runner, self.root, ["switch", repository.default_branch])
        _git(self.runner, self.root, ["pull", "--ff-only"])
        if regenerate:
            _git(self.runner, self.root, ["fetch", "origin", branch])
        _git(self.runner, self.root, ["switch", "-C", branch])

    def publish(self, task: ResumeTask, result: PipelineResult, repository: RepositoryInfo) -> PullRequest:
        if not result.success:
            raise PublishingError("Cannot publish an unsuccessful pipeline result.")
        output_directory = publishable_output_directory(self.root, task)
        relative_files = [str((output_directory / name).relative_to(self.root)) for name in PUBLISHABLE_FILES]
        missing = [path for path in relative_files if not (self.root / path).exists()]
        if missing:
            raise PublishingError(f"Cannot publish; required artifacts are missing: {', '.join(missing)}")
        _git(self.runner, self.root, ["add", "--", *relative_files])
        _git(self.runner, self.root, ["diff", "--cached", "--quiet"], allow_failure=True, expected_codes=(0, 1))
        _git(self.runner, self.root, ["commit", "-m", f"Generate resume for issue #{task.issue_number}"])
        branch = branch_name(task)
        push_arguments = ["push", "-u", "origin", branch]
        if self._existing_pull_request is not None:
            push_arguments.insert(1, "--force-with-lease")
        _git(self.runner, self.root, push_arguments)
        try:
            title = f"Generate resume: {task.company} - {task.position}"
            body = _pull_request_body(task)
            if self._existing_pull_request is not None:
                return self._existing_pull_request
            return self.github.create_pull_request(title=title, body=body, head=branch, base=repository.default_branch)
        except Exception as error:  # noqa: BLE001 - adapter failures cross the publishing boundary
            raise PublishingError(f"Pull Request creation failed: {error}") from error
        finally:
            _git(self.runner, self.root, ["switch", repository.default_branch])

    def restore_default_branch(self, repository: RepositoryInfo) -> None:
        """Return the checkout to the repository default branch after any run."""
        _git(self.runner, self.root, ["switch", repository.default_branch])


def branch_name(task: ResumeTask) -> str:
    """Return the stable branch identity for an issue."""
    if task.issue_number is None:
        raise PublishingError("Cannot publish a task without an issue number.")
    return f"resume/{task.issue_number}"


def _git(
    runner: GitRunner,
    root: Path,
    arguments: list[str],
    *,
    allow_failure: bool = False,
    expected_codes: tuple[int, ...] = (0,),
) -> str:
    try:
        result = runner(["git", *arguments], cwd=root, check=False, capture_output=True, text=True)
    except OSError as error:
        raise PublishingError(f"Git command cannot be started: git {' '.join(arguments)}") from error
    if result.returncode not in expected_codes and not allow_failure:
        detail = (result.stderr or result.stdout).strip().splitlines()
        suffix = f": {detail[-1]}" if detail else ""
        raise PublishingError(f"Git command failed: git {' '.join(arguments)}{suffix}")
    return result.stdout


def _pull_request_body(task: ResumeTask) -> str:
    issue_reference = f"Closes #{task.issue_number}" if task.issue_number is not None else ""
    return "\n".join(
        [
            f"Generated from issue #{task.issue_number}."
            if task.issue_number is not None
            else "Generated by the local resume pipeline.",
            "",
            "## Artifacts",
            "",
            *(f"- {publishable_output_directory(Path('.'), task) / name}" for name in PUBLISHABLE_FILES),
            "",
            issue_reference,
        ]
    ).strip()
