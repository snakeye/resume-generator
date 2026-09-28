# ADR-0001: Local Runner With GitHub Issues

Status: Accepted

## Context

The system needs a simple task interface and review history, while the full
professional profile and provider credentials should remain local.

## Decision

GitHub Issues are the input and persistent task state. A single local
foreground runner polls one private repository, processes one issue at a time,
and publishes successful artifacts through a Pull Request.

GitHub Actions run synthetic CI only. The MVP has no webhooks, server,
database, external queue, or concurrent workers.

## Consequences

The user must keep a local process running. Deployment and recovery remain
simple and inspectable. GitHub, Git, runner orchestration, and domain pipeline
responsibilities must stay separate.
