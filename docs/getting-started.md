# Getting Started

> [!NOTE]
> `./resume setup`, `./resume doctor`, and the generation runner are
> implemented.

## 1. Create A Private Repository

Open the public template repository, click **Use this template**, and select
**Create a new repository**.

Choose **Private** visibility. Do not use a public fork: generated resumes and
optionally the professional profile contain personal data.

## 2. Clone It

```bash
git clone <your-repository-url>
cd <your-repository-name>
```

## 3. Install Prerequisites

The first release supports macOS and Linux. Windows users should use WSL.

Install:

- Git;
- [GitHub CLI](https://cli.github.com/);
- [uv](https://docs.astral.sh/uv/).

Setup checks GitHub CLI authentication. If authentication is missing, run
`gh auth login` and rerun setup.

## 4. Run Setup

```bash
./resume setup
```

Setup will:

- verify that the repository is private;
- detect the GitHub owner, repository, and default branch;
- check GitHub authentication;
- check the local PDF toolchain;
- request the DeepSeek API key and create `.env`;
- create the four files under `data/profile/` from the synthetic examples;
- create the required GitHub labels;

Setup is idempotent. Running it again must not overwrite the profile or
secrets.

Provider settings are documented in [`.env.example`](../.env.example). The
`.env` file is loaded with `python-dotenv`; shell environment variables override
values from the file.

## 5. Fill In The Profile

Edit the files under:

```text
data/profile/
```

Follow [`profile.md`](profile.md). The file is ignored by Git by default.

Optional validation while editing:

```bash
./resume profile validate
```

The runner performs the same validation before processing work. Use
`./resume doctor` only when diagnostics are needed.

The profile is ignored by Git by default. To opt into tracking it in the
private repository history, run `./resume profile enable-git --confirm` after
reviewing the permanent-history warning. The command does not stage or commit
the file.

## 6. Start The Runner

```bash
./resume run
```

Leave this process running. It polls GitHub for resume requests and processes
one request at a time. The default console output reports each pipeline stage
and its compact result. Use `./resume run --once` for one polling cycle,
`--quiet` for only final results, or `--debug` for stage timings.

To manually process one issue without queue labels, run `./resume run --force 6`.
This uses the same generation and publishing workflow as the queue runner and
updates the existing open Pull Request for that issue when one exists.

## 7. Request A Resume

1. Open the repository's **Issues** tab.
2. Choose **Generate resume**.
3. Enter company, position, language, and the complete job description.
4. Submit the issue.

The runner changes the issue from `resume:ready` to `resume:working`, generates
and validates the resume, and creates a Pull Request.

## 8. Review The Result

The Pull Request contains:

```text
data/output/<issue-date>/<issue-number>-<company>-<position>/resume.json
data/output/<issue-date>/<issue-number>-<company>-<position>/resume.md
data/output/<issue-date>/<issue-number>-<company>-<position>/resume.tex
data/output/<issue-date>/<issue-number>-<company>-<position>/resume.pdf
data/output/<issue-date>/<issue-number>-<company>-<position>/resume.docx
data/output/<issue-date>/<issue-number>-<company>-<position>/report.md
data/output/<issue-date>/<issue-number>-<company>-<position>/run-metadata.json
```

Review the PDF and report. The same report is also retained locally at
`data/runs/<date>/<run-id>/report.md`.
Merge the Pull Request to accept the result and close the source issue.

If review shows that the profile needs more facts, edit `data/profile/`, add
the `resume:regenerate` label to the source issue, and leave the runner
running. It will update the existing Pull Request with a new generation.
