"""GitHub CLI boundary used by setup, diagnostics, and the local runner."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path


class GitHubError(RuntimeError):
    """Raised when the GitHub CLI cannot complete an operation."""


Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class RepositoryInfo:
    name_with_owner: str
    default_branch: str
    is_private: bool


@dataclass(frozen=True)
class Issue:
    """Minimal issue data required by runner orchestration."""

    number: int
    body: str
    created_at: str


@dataclass(frozen=True)
class PullRequest:
    """Minimal pull request data needed during startup recovery."""

    number: int


LIFECYCLE_LABELS = ("resume:ready", "resume:working", "resume:review", "resume:failed")
REGENERATE_LABEL = "resume:regenerate"


def run_gh(
    arguments: list[str],
    *,
    cwd: Path,
    runner: Runner = subprocess.run,
) -> str:
    """Run one GitHub CLI command without exposing credentials in errors."""
    try:
        result = runner(
            ["gh", *arguments],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise GitHubError("GitHub CLI is not installed or cannot be started.") from error

    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        message = f"GitHub CLI command failed: gh {' '.join(arguments)}"
        if detail:
            message += f" ({detail})"
        raise GitHubError(message)
    return result.stdout


def check_authentication(*, cwd: Path, runner: Runner = subprocess.run) -> None:
    """Verify that gh has an authenticated GitHub account."""
    run_gh(["auth", "status", "--hostname", "github.com"], cwd=cwd, runner=runner)


def discover_repository(*, cwd: Path, runner: Runner = subprocess.run) -> RepositoryInfo:
    """Discover repository metadata through gh rather than local assumptions."""
    raw = run_gh(
        ["repo", "view", "--json", "nameWithOwner,defaultBranchRef,isPrivate"],
        cwd=cwd,
        runner=runner,
    )
    try:
        payload = json.loads(raw)
        default_branch = payload["defaultBranchRef"]["name"]
        return RepositoryInfo(
            name_with_owner=payload["nameWithOwner"],
            default_branch=default_branch,
            is_private=payload["isPrivate"],
        )
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise GitHubError("GitHub returned invalid repository metadata.") from error


def ensure_labels(*, cwd: Path, runner: Runner = subprocess.run) -> None:
    """Create or update the lifecycle labels required by the runner."""
    labels = {
        "resume:ready": ("1f6feb", "Resume request is waiting to be processed"),
        "resume:working": ("fbca04", "Resume request is being processed"),
        "resume:review": ("0e8a16", "Generated resume is ready for review"),
        "resume:failed": ("d1242f", "Resume request failed and can be retried"),
        REGENERATE_LABEL: ("8957e5", "Regenerate the resume for the existing Pull Request"),
    }
    for name, (color, description) in labels.items():
        run_gh(
            ["label", "create", name, "--color", color, "--description", description, "--force"],
            cwd=cwd,
            runner=runner,
        )


class GitHubClient:
    """Stateful GitHub CLI adapter for one repository checkout."""

    def __init__(self, *, cwd: Path, runner: Runner = subprocess.run) -> None:
        self.cwd = cwd
        self.runner = runner

    def repository(self) -> RepositoryInfo:
        return discover_repository(cwd=self.cwd, runner=self.runner)

    def issue(self, number: int) -> Issue:
        raw = run_gh(
            [
                "issue",
                "view",
                str(number),
                "--json",
                "number,body,createdAt",
            ],
            cwd=self.cwd,
            runner=self.runner,
        )
        try:
            value = json.loads(raw)
            if not isinstance(value, Mapping):
                raise TypeError
            return _parse_issue(value)
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise GitHubError(f"GitHub returned invalid issue data for #{number}.") from error

    def ready_issues(self) -> list[Issue]:
        return self._issues("resume:ready")

    def regeneration_issues(self) -> list[Issue]:
        return self._issues(REGENERATE_LABEL)

    def working_issues(self) -> list[Issue]:
        return self._issues("resume:working")

    def set_lifecycle(self, issue_number: int, label: str) -> None:
        if label not in LIFECYCLE_LABELS:
            raise GitHubError(f"Unknown resume lifecycle label: {label}")
        arguments = ["issue", "edit", str(issue_number)]
        for current in LIFECYCLE_LABELS:
            if current != label:
                arguments.extend(["--remove-label", current])
        arguments.extend(["--add-label", label])
        run_gh(arguments, cwd=self.cwd, runner=self.runner)

    def claim_regeneration(self, issue_number: int) -> None:
        """Claim a regeneration request and remove its one-shot action label."""
        arguments = ["issue", "edit", str(issue_number), "--remove-label", REGENERATE_LABEL]
        for current in LIFECYCLE_LABELS:
            if current != "resume:working":
                arguments.extend(["--remove-label", current])
        arguments.extend(["--add-label", "resume:working"])
        run_gh(arguments, cwd=self.cwd, runner=self.runner)

    def comment(self, issue_number: int, body: str) -> None:
        if not body.strip():
            raise GitHubError("Issue comment must not be empty.")
        run_gh(["issue", "comment", str(issue_number), "--body", body], cwd=self.cwd, runner=self.runner)

    def edit_title(self, issue_number: int, title: str) -> None:
        if not title.strip():
            raise GitHubError("Issue title must not be empty.")
        run_gh(["issue", "edit", str(issue_number), "--title", title], cwd=self.cwd, runner=self.runner)

    def pull_requests_for_branch(self, branch: str) -> list[PullRequest]:
        raw = run_gh(
            ["pr", "list", "--state", "open", "--head", branch, "--json", "number"],
            cwd=self.cwd,
            runner=self.runner,
        )
        try:
            values = json.loads(raw)
            if not isinstance(values, list) or not all(isinstance(value, Mapping) for value in values):
                raise TypeError
            return [PullRequest(number=value["number"]) for value in values]
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise GitHubError("GitHub returned invalid pull request data.") from error

    def create_pull_request(self, *, title: str, body: str, head: str, base: str) -> PullRequest:
        raw = run_gh(
            ["pr", "create", "--base", base, "--head", head, "--title", title, "--body", body],
            cwd=self.cwd,
            runner=self.runner,
        ).strip()
        try:
            number = int(raw.rstrip("/").rsplit("/", 1)[-1])
        except (TypeError, ValueError) as error:
            raise GitHubError("GitHub returned an invalid Pull Request URL.") from error
        return PullRequest(number=number)

    def _issues(self, *labels: str) -> list[Issue]:
        label_arguments = [argument for label in labels for argument in ("--label", label)]
        raw = run_gh(
            [
                "issue",
                "list",
                "--state",
                "open",
                *label_arguments,
                "--limit",
                "100",
                "--json",
                "number,body,createdAt",
            ],
            cwd=self.cwd,
            runner=self.runner,
        )
        try:
            values = json.loads(raw)
            if not isinstance(values, list) or not all(isinstance(value, Mapping) for value in values):
                raise TypeError
            issues = [_parse_issue(value) for value in values]
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise GitHubError("GitHub returned invalid issue data.") from error
        return sorted(issues, key=lambda issue: (issue.created_at, issue.number))


def _parse_issue(value: Mapping[str, object]) -> Issue:
    return Issue(
        number=value["number"],
        body=value.get("body", ""),
        created_at=value["createdAt"],
    )
