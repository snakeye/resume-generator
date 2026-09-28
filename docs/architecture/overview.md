# Architecture Overview

## Components

```text
GitHub Issue
    |
    v
Local runner ---- GitHub API
    |
    +---- profile and local run data
    |
    +---- LLM provider
    |
    +---- resume pipeline
    |
    +---- PDF renderer
    |
    +---- Git branch and Pull Request
```

## Responsibilities

GitHub manages:

- task input;
- queue and lifecycle state;
- discussion and human review;
- published artifact history.

The runner manages:

- polling and orchestration;
- local process exclusivity;
- Git and GitHub side effects;
- failure handling and reconciliation.

The pipeline manages:

- vacancy analysis;
- evidence matching and selection;
- resume generation, assembly, and validation;
- rendering inputs and publishable artifacts.

Individual stages do not know about GitHub or Git. LLM providers do not
receive GitHub credentials or filesystem access.

## Main Flow

```text
Issue Form
  -> ResumeTask
  -> vacancy requirements
  -> evidence matches
  -> selected facts
  -> generated claims with provenance
  -> assembled resume
  -> validation
  -> TeX and PDF
  -> sanitized output
  -> Pull Request
```

The profile is the source of truth. Vacancy text only influences relevance,
terminology, and presentation.

## Simplicity

The system uses one process, one checkout, and one task at a time. There is no
database, message queue, webhook, container requirement, or distributed lock
in the MVP.
