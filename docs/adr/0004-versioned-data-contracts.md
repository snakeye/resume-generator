# ADR-0004: Versioned Data Contracts

Status: Accepted

## Context

LLM responses and intermediate artifacts cross trust and persistence
boundaries. Implicit dictionaries make drift hard to diagnose.

## Decision

Persisted and LLM-facing contracts have explicit schema versions and strict
schemas. Requirements, matches, and claims use explicit source paths. Profile
facts use stable index paths such as `work[0].facts[1]`. Artifacts
record producer stage, run identity, and relevant schema and prompt versions.

Python representations remain simple dataclasses, typed mappings, or plain
values. Schema versioning does not justify a large object model.

## Consequences

Invalid data fails at the boundary with actionable diagnostics. Reordering
profile arrays changes source paths, so profile edits and generated artifacts
must be evaluated together. Contract changes require deliberate versioning and
fixtures.
