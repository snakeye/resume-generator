# ADR-0010: Generalized Evidence Sources

Status: Accepted

## Context

Evidence matching originally addressed only work facts. Structured profile
sections such as languages and education were rendered as passthrough data but
could not cover vacancy requirements.

## Decision

Evidence matches use `source_paths` rather than work-specific `fact_paths`.
Source paths are deterministic index paths. The supported sources are
`work[i].facts[j]`, `work[i].skills[j]`, `languages[i]`, and `education[i]`.

Work positions remain separate matching groups. Languages and education use a
profile-level matching group and are represented automatically when their
profile sections are passed through to the resume. Work skills are evidence
sources represented by the generated skills section. Work fact selection
remains responsible only for selecting work facts for generated content.

## Consequences

Coverage can be supported by any addressable profile source without treating
vacancy terminology as evidence. New profile sections can join the same
contract by adding source indexing and a representation policy. Existing
work-only provider fixtures are accepted during the contract transition, while
new persisted matching output uses `source_paths`.
