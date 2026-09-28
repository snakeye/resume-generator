# ADR-0012: Multiple Resume Renderings

Status: Accepted

## Context

The assembled `ResumeDocument` is already the canonical, validated resume
content. PDF is the primary submission artifact, but users also need a simple
text representation and an editable office document. Deriving these formats
from PDF or LaTeX would lose structure and add unnecessary conversion tools.

## Decision

Render `ResumeDocument` directly into Markdown, LaTeX/PDF, and DOCX. Markdown
and DOCX are publishable sibling artifacts of the same run. DOCX is generated
with `python-docx` and is an editable convenience format; it is not required to
match the PDF layout or page count.

All renderers are deterministic and receive only the assembled document. The
exact publishable allowlist includes `resume.md` and `resume.docx` alongside the
existing JSON, TeX, PDF, report, and metadata files.

## Consequences

The project has no dependency on Pandoc or LibreOffice. DOCX validation checks
that the document is structurally readable and contains the generated content,
while PDF validation continues to check extraction, links, and layout-specific
properties. More artifacts are published, but every format remains traceable to
the same canonical JSON.
