import json
import subprocess

from resume_generator.github import GitHubClient


def completed(stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def test_ready_issues_sort_oldest_first(tmp_path):
    responses = [
        json.dumps(
            [
                {
                    "number": 2,
                    "body": "body 2",
                    "createdAt": "2026-02-01T00:00:00Z",
                },
                {
                    "number": 1,
                    "body": "body 1",
                    "createdAt": "2026-01-01T00:00:00Z",
                },
                {
                    "number": 3,
                    "body": "body 3",
                    "createdAt": "2026-01-01T00:00:00Z",
                },
            ]
        )
    ]

    def fake_runner(*_args, **_kwargs):
        return completed(responses.pop(0))

    issues = GitHubClient(cwd=tmp_path, runner=fake_runner).ready_issues()

    assert [issue.number for issue in issues] == [1, 3, 2]


def test_issue_fetches_one_issue_without_labels(tmp_path):
    calls = []

    def fake_runner(arguments, **_kwargs):
        calls.append(arguments)
        return completed(
            json.dumps(
                {
                    "number": 6,
                    "body": "body",
                    "createdAt": "2026-09-28T10:00:00Z",
                }
            )
        )

    result = GitHubClient(cwd=tmp_path, runner=fake_runner).issue(6)

    assert result.number == 6
    assert calls == [
        [
            "gh",
            "issue",
            "view",
            "6",
            "--json",
            "number,body,createdAt",
        ]
    ]


def test_set_lifecycle_removes_other_lifecycle_labels(tmp_path):
    calls = []

    def fake_runner(arguments, **_kwargs):
        calls.append(arguments)
        return completed("")

    GitHubClient(cwd=tmp_path, runner=fake_runner).set_lifecycle(42, "resume:working")

    assert calls == [
        [
            "gh",
            "issue",
            "edit",
            "42",
            "--remove-label",
            "resume:ready",
            "--remove-label",
            "resume:review",
            "--remove-label",
            "resume:failed",
            "--add-label",
            "resume:working",
        ]
    ]


def test_claim_regeneration_replaces_lifecycle_and_action_labels(tmp_path):
    calls = []

    def fake_runner(arguments, **_kwargs):
        calls.append(arguments)
        return completed("")

    GitHubClient(cwd=tmp_path, runner=fake_runner).claim_regeneration(42)

    assert calls == [
        [
            "gh",
            "issue",
            "edit",
            "42",
            "--remove-label",
            "resume:regenerate",
            "--remove-label",
            "resume:ready",
            "--remove-label",
            "resume:review",
            "--remove-label",
            "resume:failed",
            "--add-label",
            "resume:working",
        ]
    ]


def test_edit_title_updates_issue_title(tmp_path):
    calls = []

    def fake_runner(arguments, **_kwargs):
        calls.append(arguments)
        return completed("")

    GitHubClient(cwd=tmp_path, runner=fake_runner).edit_title(42, "[Resume] Example — Engineer — 2026-09-28")

    assert calls == [["gh", "issue", "edit", "42", "--title", "[Resume] Example — Engineer — 2026-09-28"]]
