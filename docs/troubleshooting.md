# Troubleshooting

> [!NOTE]
> `setup`, `doctor`, and resume generation are implemented. The roadmap tracks
> release follow-up work rather than missing core commands.

Start with:

```bash
./resume doctor
```

The command should identify the first blocking problem and print the exact
recovery command.

`doctor` checks local tools, GitHub authentication and repository visibility,
then reports whether the profile and `.env` exist. It does not modify files.

## GitHub Authentication Is Missing

```bash
gh auth login
gh auth status
```

Ensure the authenticated account can read and write the private repository.

## Repository Must Be Private

The normal setup refuses public repositories because Pull Requests contain
personal resumes. Change repository visibility before adding real profile
data. Public repositories are supported only for synthetic demonstrations.

## Profile Is Invalid

```bash
./resume profile validate
```

Use the reported YAML path and compare it with
`data/examples/profile/profile.example.yaml`. Validation does not silently
repair profile data.

## Enabling Git Storage For The Profile

Use the explicit opt-in only in a private repository:

```bash
./resume profile enable-git --confirm
```

The command changes `.gitignore` but does not stage or commit the profile.
Review the diff before deciding whether to add it to Git.

## Runner Does Not See An Issue

Check that:

- the issue is open;
- it has exactly one lifecycle label, or has `resume:regenerate` when an
  existing Pull Request should be regenerated;
- the Issue Form version is supported;
- `./resume doctor` can access the repository;
- the polling interval has elapsed.

## Repository Contains Local Changes

The runner never resets or cleans unexpected work. Inspect it with:

```bash
git status
```

Commit, stash, or otherwise handle your changes, then restart the runner.

## Issue Is Stuck In `resume:working`

Stop duplicate runner processes and start one runner again. Startup recovery
reconciles an existing Pull Request or returns interrupted work to the queue.

## DeepSeek Request Failed

Check that `DEEPSEEK_API_KEY` exists in `.env`, then run `./resume doctor`.
Provider timeouts and rate limits remain recoverable infrastructure failures.

## Provider Configuration Is Invalid

Run:

```bash
./resume doctor
```

Check the reported setting in `.env`. Numeric settings such as
`LLM_TIMEOUT_SECONDS` and `LLM_RETRIES` must contain valid positive values.

## PDF Compilation Failed

Run `./resume doctor` to check the renderer. Detailed local diagnostics are in
`data/logs/runner.log`; GitHub comments intentionally omit full logs and
sensitive payloads.

## Pull Request Was Not Created

Do not create a second issue. Restart the runner. It must inspect the existing
branch and Pull Request before deciding whether to regenerate or finish
publishing.

## Regeneration Does Not Start

Check that:

- the source issue is open;
- the `resume:regenerate` label is present;
- if the issue is `resume:review`, it has one open Pull Request from
  `resume/<issue-number>`; failed issues are retried without an existing PR;
- the local profile is valid with `./resume profile validate`;
- the repository is clean if profile files are tracked in Git.
