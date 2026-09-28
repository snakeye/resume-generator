# ADR-0009: Pydantic Runtime Contracts

Status: Accepted

## Context

Profile, provider, pipeline, and persisted artifact boundaries need strict
validation, useful field paths, and immutable normalized values. Hand-written
validation duplicated type checks and conversion rules across these boundaries.

## Decision

Use Pydantic v2 for runtime validation of application data models. Models use
forbidden extra fields, strict scalar fields where coercion would be unsafe,
and frozen values after validation. Domain-specific rules such as date ranges
remain explicit validators.

Application environment configuration uses `pydantic-settings` and loads the
repository `.env` through `python-dotenv` at the application boundary. Provider
code receives validated settings and does not read process environment state.

Pydantic models are the only maintained contract definitions. Runtime Python
validation does not depend on a second hand-written schema layer.

## Consequences

Validation errors have structured locations and models can emit schemas when an
external contract is needed. Pydantic is a production dependency, and
migrations must preserve the rule that validation never silently rewrites
profile or generated content.
