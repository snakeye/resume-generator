# Data Layout And Artifacts

All working data uses one root:

```text
data/
├── profile/
├── examples/
├── runs/
├── output/
├── cache/
└── logs/
```

## Profile

`data/profile/` contains the user-maintained source of truth. `profile.yaml`
contains career data; `preferences.yaml`, `voice.yaml`, and `aliases.yaml`
contain candidate-specific presentation and matching configuration. The whole
directory is ignored by default. Private Git storage is an explicit opt-in.

## Examples

`data/examples/` is tracked and fully synthetic. Examples must not be derived
from real profiles by anonymizing names.

## Runs

Each attempt writes local inspectable artifacts:

```text
data/runs/2026-01-01/issue-142-20260101120000000000/
├── input/
│   └── issue-body.md
├── stages/
├── debug/
├── report.md
└── run-metadata.json
```

Run directories are grouped by their UTC creation date and created exclusively
for a new `run_id`. Artifact writes are atomic: a final path is either complete
or absent, and a failed write does not leave a temporary file behind.

The directory may contain prompts, raw provider responses, and profile-derived
data. It is always ignored.

## Output

Only the publishable subset enters Git:

```text
data/output/2026-01-01/142-example-gmbh-senior-software-engineer/
├── resume.json
├── resume.md
├── resume.tex
├── resume.pdf
├── resume.docx
├── report.md
└── run-metadata.json
```

Publishing uses an exact file allowlist. It never uses `git add .`.

## Application Resources

Prompts and resume templates are versioned application code:

```text
src/resume_generator/resources/
├── prompts/
└── templates/
```

They are loaded with `importlib.resources`, not paths relative to the current
working directory.

## Validation And Rendering

`validation.py` returns a versioned report with warnings and blocking errors. It
never rewrites the assembled resume. `rendering.py` treats `resume.json` as the
canonical input, produces `resume.md`, reviewable `resume.tex`, editable
`resume.docx`, and compiles `resume.pdf` through an injectable `xelatex`
compiler boundary. The assembled JSON contains
 grouped experience roles, an optional source-backed Earlier Experience block,
 education, and languages; grouping is presentation data and does not change
 bullet provenance. PDF text is checked through the
local `pdftotext` command when rendering is run.
