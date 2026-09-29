# Contributing

The project is being built in small, independently verifiable stages. Start
with [`docs/index.md`](docs/index.md) and the accepted
[ADRs](docs/adr/README.md).

Development and debugging happen in the private development repository.
The public template and static demo are release outputs; do not use them for
real profile data or as development branches. See the
[`repository model`](docs/repository-model.md) before preparing a release.

## Local Checks

```bash
uv sync --dev
uv run ruff format .
uv run ruff check .
uv run pytest
```

Each change should solve one concrete problem. Prefer functions, standard
library features, and existing project code over new abstractions or
dependencies. Update user documentation whenever a public command, profile
field, setup step, or generated artifact changes.

Never use real candidate data in examples, fixtures, issues, or bug reports.
