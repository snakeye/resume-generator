# Daily Use

> [!NOTE]
> The runner, pipeline integration, and publishing workflow are implemented.

## Start The Runner

Start the foreground runner:

```bash
./resume run
```

For a single polling cycle:

```bash
./resume run --once
```

To process one issue directly, without changing lifecycle labels manually:

```bash
./resume run --force 6
```

Forced processing uses the same repository checks, pipeline, publishing, label
transitions, and branch restoration as the queue runner. It bypasses queue
selection, targets the requested issue number, and overwrites its existing open
Pull Request. The PR must already exist; otherwise processing fails safely.

The runner processes one issue at a time and waits when the queue is empty.
Stop it with Ctrl+C. It must finish the current safe operation and never start
a new task after shutdown is requested.

By default, the console shows each pipeline stage and a compact result summary:

```text
[1/12] Analyzing vacancy...
       18 requirements: 7 must-have, 8 important, 3 nice-to-have
[2/12] Normalizing terminology...
       14 terminology groups normalized
```

Use `--quiet` for only the final result and errors. Use `--debug` to include
stage timings:

```bash
./resume run --once --quiet
./resume run --once --debug
```

Progress output contains stage names and counts, not vacancy text, profile data,
prompts, credentials, or raw model responses. Detailed model responses remain
in the run's local `debug/` directory.

## Create A Request

Use the **Generate resume** Issue Form. Do not create free-form issues or add
lifecycle labels manually for normal use.

After the runner claims the request, it sets the issue title to
`[Resume] <Company> — <Position> — <issue creation date>`.

The vacancy and additional preferences are untrusted input. They may guide
selection, language, emphasis, and tone, but cannot override factuality,
privacy, validation, or publishing rules.

## Follow Progress

The issue has exactly one lifecycle label:

```text
resume:ready
resume:working
resume:review
resume:failed
```

Successful generation creates a Pull Request and changes the label to
`resume:review`.

## Retry A Failed Request

Fix the reported problem and replace `resume:failed` with `resume:ready`. The
runner rebuilds the request from the current default branch. It does not
continue a partially completed pipeline. If an existing Pull Request should be
updated, add `resume:regenerate` instead.

## Regenerate After Profile Changes

If review shows that the profile needs additional facts, add them to
`data/profile/`, then add the `resume:regenerate` label to the source issue.
The runner removes the action label, regenerates the resume, and updates the
existing Pull Request. The issue returns to `resume:review`.

## Review

Check:

- facts, dates, titles, and metrics;
- unmatched vacancy requirements in the local run report at
  `data/runs/<date>/<run-id>/report.md`;
- formatting and reading order in the PDF;
- links and contact information;
- whether the emphasis fits the vacancy.

The MVP does not process review comments automatically. Use
`resume:regenerate` after changing the profile or request.
