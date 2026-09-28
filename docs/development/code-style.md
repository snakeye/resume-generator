# Code Style

## Primary Rule

Code should be as simple as a correct solution allows. Prefer readability,
explicit data flow, and deletion over speculative flexibility.

Use this order:

1. Do not build what is not required.
2. Reuse project code.
3. Use the standard library.
4. Use native platform functionality.
5. Use an installed dependency.
6. Write the minimum new code.

## Functions And Classes

Functions are the default. Introduce a class only when instances own state,
resources, or a meaningful lifecycle, or when multiple real implementations
require substitution.

Do not use classes as namespaces. Avoid `Manager`, `Service`, `Helper`, and
`Utils` types that only group stateless methods.

Dataclasses are appropriate for explicit data records such as `ResumeTask` and
`ValidationIssue`. A protocol is appropriate when production and test
implementations both use the same boundary.

## Control Flow

Handle invalid and special cases first with guard clauses. Keep the happy path
flat and readable.

```python
def select_issue(issue: Issue) -> ResumeTask | None:
    if issue.is_pull_request:
        return None

    if not issue.has_label("resume:ready"):
        return None

    return parse_resume_task(issue)
```

Rules:

- avoid nesting deeper than two levels;
- omit `else` after `return`, `raise`, `continue`, or `break`;
- give complex conditions meaningful names;
- keep one abstraction level per function;
- avoid boolean flags that switch a function between different jobs.

Functions usually stay below 20 logical lines. More than 30 requires careful
review. This is a readability signal, not a reason to create meaningless
one-line helpers. Ruff enforces a maximum cyclomatic complexity of eight.

## Names

Functions use domain verbs such as `parse_resume_task`,
`select_relevant_facts`, and `render_resume_pdf`. Boolean names begin with
`is_`, `has_`, `can_`, or `should_`.

Use one term for one concept throughout the project. Avoid generic names such
as `process_data`, `handle_item`, or `do_work`. Comments explain why a choice
exists, not what an obvious line does.

## Architecture

Do not add without demonstrated need:

- a factory for one implementation;
- service or repository layers that repeat functions;
- dependency injection containers;
- event buses or hooks;
- a generic pipeline framework;
- runtime plugin loading;
- wrappers that add no project semantics;
- configuration for values that never vary.

The explicit sequence of pipeline functions is preferable to a framework.

## Tooling

Ruff is the only formatter and linter. Do not add Black, isort, or Flake8.

```bash
uv run ruff format .
uv run ruff check .
uv run pytest
```
