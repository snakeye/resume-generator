# Repository Model

The project uses three repositories with different responsibilities:

| Repository | Visibility | Purpose | Allowed data |
| --- | --- | --- | --- |
| [`resume-generator-private`](https://github.com/snakeye/resume-generator-private) | Private | Development, debugging, release preparation, and real local runs | Real profile, local runs, provider diagnostics, and private branches |
| [`resume-generator`](https://github.com/snakeye/resume-generator) | Public template | User-facing release distributed through **Use this template** | Source code, documentation, tests, and synthetic examples only |
| [`resume-generator-demo`](https://github.com/snakeye/resume-generator-demo) | Public | Static showcase of generated output | Synthetic profile, vacancy, and generated artifacts only |

## Development And Release Flow

```text
private development
    -> tests and release checks
    -> sanitized export
    -> public template release
    -> synthetic demo update
```

Development and debugging happen only in `resume-generator-private`. Its real
profile, run artifacts, raw provider responses, credentials, and resume
branches never move to a public repository.

The public template is produced from a clean export with a new Git history. It
is the starting point for users, who create a separate private repository from
the template before adding a real profile or API key.

The public demo is not a runnable user repository. It contains a pre-generated
synthetic example for reviewing the output formats and report. It must not
contain the local runner, credentials, raw provider responses, or real profile
data.

## Release Rules

- Make and test code changes in the private repository.
- Run the full quality and synthetic acceptance checks before exporting.
- Review the export file list and scan all exported content for secrets and PII.
- Publish the template and demo with independent, clean histories.
- Update public README links and release notes when repository roles change.
- Never use a public repository as the source for real candidate data.

## User Workflow

Users should:

1. Open the [public template](https://github.com/snakeye/resume-generator).
2. Create a new **private** repository with **Use this template**.
3. Clone that private repository and run `./resume setup`.
4. Use the [static demo](https://github.com/snakeye/resume-generator-demo) only
   to preview synthetic output.
