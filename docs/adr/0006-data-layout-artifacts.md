# ADR-0006: Unified Data Directory And Artifact Policy

Status: Accepted

## Context

Separate top-level profile, run, output, cache, and log directories make the
template harder to understand and obscure privacy boundaries.

## Decision

All working data lives under `data/`. Real profile, runs, cache, and logs are
ignored. Synthetic examples are tracked. Only the allowlisted final files
under `data/output/<issue-date>/<issue-number>-<company>-<position>/` may enter
resume branches.

Prompts and templates are application resources under
`src/resume_generator/resources/`.

## Consequences

The repository root remains small and data policies are obvious. Publishing
must stage explicit paths and never use `git add .`.
