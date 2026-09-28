# ADR-0005: Provider Abstraction With DeepSeek First

Status: Accepted

## Context

The first implementation can reuse proven DeepSeek behavior from `cvbot`, but
the pipeline should not depend on one provider's HTTP response shape.

## Decision

Use one small structural protocol for JSON generation. DeepSeek is the only
working provider in the first release. OpenAI and Ollama names resolve to
explicit unsupported stubs until implemented. A fake provider supports tests.

There is no provider plugin framework, base-class hierarchy, or silent
fallback.

## Consequences

Pipeline code stays provider-independent without speculative infrastructure.
Adding a provider requires shared contract tests and explicit documentation.
