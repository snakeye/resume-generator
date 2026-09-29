# Implementation Roadmap

Each phase should be independently testable and keep the documented quick
start accurate.

## 0. Foundation

- documentation, ADRs, agent instructions, Issue Form, Ruff, pytest, and CI;
- safe `data/` layout and synthetic profile;
- no production implementation.

## 1. CLI And Setup

- `./resume` wrapper; **implemented**;
- `setup`, `doctor`, and profile initialization; **implemented**;
- GitHub repository discovery through `gh`; **implemented**;
- private repository check and label bootstrap; **implemented**.

## 2. Profile And Contracts

- YAML loader and strict schema; **implemented**;
- index-addressed work facts without manual IDs; **implemented**;
- normalized internal representation; **implemented**;
- profile validation; **implemented**;
- profile storage modes; **implemented**.

## 3. Pipeline Kernel

- run directories and atomic artifacts; **implemented**;
- explicit stage sequence; **implemented**;
- versioned run metadata; **implemented**;
- stage schema validation; **implemented**;
- deterministic cache keys where measurements justify caching.

## 4. LLM Provider

- minimal provider protocol; **implemented**;
- DeepSeek implementation; **implemented**;
- fake provider for tests; **implemented**;
- explicit OpenAI and Ollama unsupported stubs; **implemented**;
- retries, structured JSON, usage, and safe diagnostics; **implemented**.

## 5. Vacancy And Evidence

- Issue Form parser; **implemented**;
- vacancy analysis and requirement IDs; **implemented**;
- terminology normalization; **implemented**;
- evidence matching and coverage; **implemented**;
- prompt-injection regression tests; **implemented**

## 6. Resume Content

- fact selection; **implemented**;
- headline; **implemented**;
- bullets; **implemented**;
- summary; **implemented**;
- skills; **implemented**;
- voice; **implemented**;
- claim-to-fact provenance; **implemented**;
- deterministic assembly; **implemented**.

## 7. Validation And Rendering

- factual, coverage, and text validation; **implemented**;
- LaTeX rendering and PDF compilation; **implemented**;
- PDF extraction and expected-content checks; **implemented**;
- Markdown and DOCX rendering and validation; **implemented**;
- validation never rewrites content; **implemented**;
- real compiler smoke test remains an optional local check, not a CI requirement.

## 8. GitHub Runner

- polling and lifecycle transitions; **runner core implemented**;
- local process lock and graceful shutdown; **runner core implemented**;
- dirty worktree protection; **runner core implemented**;
- infrastructure failure handling and startup reconciliation; **runner core implemented**;
- pipeline adapter and publishable output integration; **implemented**;
- end-to-end queue processing with a real configured pipeline; **implemented**.

## 9. Publishing

- allowlisted artifact packaging; **implemented**;
- branch, commit, push, and Pull Request creation; **implemented**;
- duplicate branch/PR recovery; **implemented**;
- end-to-end synthetic test; **implemented**.

## 10. Template Release

- private development repository separated from public release repositories;
- public template repository created with a clean synthetic export;
- public static demo repository created with synthetic generated artifacts;
- public repository links and privacy boundaries documented;
- clean onboarding test on macOS and Linux;
- full Git history privacy review for the private source and every public export;
- release acceptance checks and `v0.1.0`.
