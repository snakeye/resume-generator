# ADR-0003: Stage-Oriented Pipeline

Status: Accepted

## Context

LLM generation is easier to inspect and validate when selection, writing, and
rendering are not hidden in one large request.

## Decision

The pipeline is an explicit sequence of small stages with one responsibility
each. Deterministic work stays in Python. LLM stages are used only where
language understanding or generation is necessary.

Stages do not access GitHub or Git. The implementation uses ordinary functions
unless real state or resource ownership justifies a class. No generic pipeline
framework is introduced for the MVP.

## Consequences

Intermediate results can be inspected and tested. More contracts exist, but
their sequence remains visible in normal code rather than configuration or a
framework.
