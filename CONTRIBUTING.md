# Contributing

The project is being built in small, independently verifiable stages. Start
with [`docs/index.md`](docs/index.md) and the accepted
[ADRs](docs/adr/README.md).

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
