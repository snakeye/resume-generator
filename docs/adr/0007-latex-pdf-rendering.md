# ADR-0007: LaTeX PDF Rendering

Status: Accepted

## Context

The related `cvbot` project has a proven JSON-to-Jinja-to-XeLaTeX resume layout.
PDF is the primary submission artifact, and TeX is useful for review and manual
correction. The template must be copied into this repository so rendering has
no runtime dependency on the related project.

## Decision

Use a versioned Jinja2 LaTeX template copied from the proven `cvbot` layout and
stored under application resources. Use `xelatex` behind a small callable
boundary, with configurable main and fallback fonts and a deterministic second
pass for references.

Publish JSON, TeX, and PDF. Validate compilation, non-empty output, extracted
text, expected sections, page count, and links before publishing.

## Consequences

The project reuses the tested visual decisions from `cvbot`, but not its code,
paths, data model, or runtime. The assembled contract contains grouped company
experience, education, and languages required by the layout. Unit tests use a
fake compiler and extractor; a real synthetic PDF smoke test is an optional
local verification and is not a CI prerequisite.
