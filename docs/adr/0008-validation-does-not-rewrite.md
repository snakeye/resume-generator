# ADR-0008: Validation Does Not Rewrite Content

Status: Accepted

## Context

If validation silently edits generated text, the source of the final wording
and its evidence becomes difficult to inspect.

## Decision

Validators only accept, warn, or reject. They never silently rewrite generated
content. Blocking failures prevent publishing and identify the stage, claim,
and evidence involved.

## Consequences

Repairs happen in the responsible generation stage or through an explicit
retry. The audit trail remains understandable.
