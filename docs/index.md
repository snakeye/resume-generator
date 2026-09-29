# Documentation

Resume Generator is developed in a private repository and released as a
public GitHub template for producing evidence-based, vacancy-specific resumes
through GitHub Issues. Generation runs locally so the user's full professional
profile does not need to leave their machine or enter GitHub Actions.

Read the [repository model](repository-model.md) first to understand the
boundary between private development, the public template, and the static demo.

## For Users

Read these pages in order:

1. [`getting-started.md`](getting-started.md)
2. [`profile.md`](profile.md)
3. [`daily-use.md`](daily-use.md)
4. [`privacy.md`](privacy.md)
5. [`troubleshooting.md`](troubleshooting.md)

## Product

- [`product/vision.md`](product/vision.md)
- [`product/scope.md`](product/scope.md)
- [`product/glossary.md`](product/glossary.md)
- [`roadmap.md`](roadmap.md)

## Architecture

- [`architecture/overview.md`](architecture/overview.md)
- [`architecture/data-layout.md`](architecture/data-layout.md)
- [`architecture/security.md`](architecture/security.md)
- [`architecture/providers.md`](architecture/providers.md)

## Specifications

- [`specifications/resume-pipeline.md`](specifications/resume-pipeline.md)
- [`specifications/github-issues-runner.md`](specifications/github-issues-runner.md)

## Development

- [`development/code-style.md`](development/code-style.md)
- [`development/testing.md`](development/testing.md)
- [`development/prompts.md`](development/prompts.md)
- [`development/adding-provider.md`](development/adding-provider.md)
- [`adr/README.md`](adr/README.md)

## Sources Of Truth

When documents disagree, use this order:

1. Accepted ADRs for architectural decisions.
2. Specifications for observable behavior and contracts.
3. User documentation for supported workflows.
4. Development guides for implementation conventions.

Update conflicting documents in the same change rather than relying on this
precedence permanently.
