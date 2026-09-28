# Resume Generator

Generate a resume tailored to a vacancy from a professional profile that you
control. GitHub Issues are the task queue, a local runner does the private
work, and every successful request produces a Pull Request for human review.

> [!IMPORTANT]
> Profile processing, resume content validation, and local LaTeX/PDF rendering
> are implemented. The local runner, pipeline integration, and publishing
> through Pull Requests are implemented.

## How It Works

```text
GitHub Issue -> local runner -> validated resume -> Pull Request
```

- Your professional profile is the only source of career facts.
- Vacancy text may change selection and wording, but cannot invent experience.
- Real profile data stays local by default.
- GitHub Actions never receive the real profile or LLM credentials.
- A human reviews every generated resume before merge.

## Quick Start

1. Click **Use this template** and create a **private** repository.
2. Clone your new repository.
3. Configure the project:

   ```bash
   ./resume setup
   ```

4. Fill in the files under `data/profile/`.
5. Start the runner:

   ```bash
   ./resume run
   ```

   To process one issue directly, use `./resume run --force 6`.

6. Create a **Generate resume** issue and wait for the generated Pull Request.

The setup command will guide GitHub authentication when needed, create labels,
detect the repository and default branch, configure DeepSeek, prepare the
profile, and verify the PDF toolchain. `./resume doctor` is available when
diagnostics are needed but is not a required setup step.

## Requirements

The first release targets macOS and Linux. Windows is supported through WSL.

- Git
- [GitHub CLI](https://cli.github.com/)
- [uv](https://docs.astral.sh/uv/)
- a DeepSeek API key

PDF toolchain installation will be checked and explained by `./resume setup`.

## Profile

The profile configuration lives in these files:

```text
data/profile/profile.yaml
data/profile/preferences.yaml
data/profile/voice.yaml
data/profile/aliases.yaml
```

Start with the files under `data/examples/profile/`. See
[`docs/profile.md`](docs/profile.md) for every field and practical examples.
The profile remains local by default; private Git tracking is an explicit
opt-in via `./resume profile enable-git --confirm`.

## Privacy

The profile, run history, cache, and logs are ignored by Git. Generated
resumes are committed to issue branches because they must be reviewed in Pull
Requests. They contain personal data and should only be used in a private
repository.

Read [`docs/privacy.md`](docs/privacy.md) before enabling profile storage in
Git.

## Documentation

- [Getting started](docs/getting-started.md)
- [Writing the profile](docs/profile.md)
- [Daily use](docs/daily-use.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Architecture and development](docs/index.md)
- [Implementation roadmap](docs/roadmap.md)

## Development

The project intentionally favors small functions, explicit data flow, early
returns, and classes only when instances own state or resources.

```bash
uv sync --dev
uv run ruff format .
uv run ruff check .
uv run pytest
```

See [`docs/development/code-style.md`](docs/development/code-style.md).
