# Privacy

The project processes professional history, contact details, vacancy text,
and generated resumes. Treat all of them as potentially sensitive.

## Default Storage

These paths stay local and are ignored by Git:

```text
.env
data/profile/
data/runs/
data/cache/
data/logs/
```

`data/examples/` contains synthetic data only.

## Published Artifacts

Successful issue branches contain only:

```text
resume.json
resume.md
resume.tex
resume.pdf
resume.docx
report.md
run-metadata.json
```

The generation report is also kept locally at
`data/runs/<date>/<run-id>/report.md`.

These files still contain personal data. The repository should therefore be
private. Removing a file in a later commit does not remove it from Git history.

`run-metadata.json` records hashes and versions rather than issue, profile,
configuration, or prompt contents. Hashes are not a substitute for keeping the
repository private because they can still identify whether known source data
was used.

## LLM Provider

Only the minimum structured data required by each stage should be sent to the
configured provider. Provider privacy, retention, and regional processing
policies are outside this repository and must be reviewed by the user.

Never send:

- GitHub tokens;
- `.env`;
- SSH keys;
- unrelated local files;
- complete debug logs.

## Private Git Profile Mode

Tracking the files in `data/profile/` is an explicit opt-in available only for
a private repository. Enable it only after reviewing the permanent history
warning:

```bash
./resume profile enable-git --confirm
```

The command does not stage or commit files. Local storage is safer and remains
the default.

## Public Demonstrations

The project has two public repositories with different purposes:

- The [public template](https://github.com/snakeye/resume-generator) contains
  source code, documentation, tests, and synthetic examples. It must not contain
  a real profile, generated run, credential, or private branch.
- The [static demo](https://github.com/snakeye/resume-generator-demo) contains
  only a synthetic profile, synthetic vacancy, and pre-generated synthetic
  artifacts. It does not contain the runner, credentials, raw provider output,
  or local run history.

Do not derive public examples from a real profile by changing names. The private
development repository is the only place for real profile data and debugging
artifacts. Users must create their own private repository from the public
template before adding personal data.
