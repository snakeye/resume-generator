# ADR-0011: Regenerate Reviewed Resumes In The Existing Pull Request

Status: Accepted

## Context

Profile facts may be improved after a generated resume has been opened for
review. Creating another issue or Pull Request would split the review history
and make the current result ambiguous.

## Decision

The source issue may receive the one-shot action label `resume:regenerate` while
its lifecycle label remains `resume:review`. The local runner claims the action
by removing the label and changing the lifecycle to `resume:working`.

The action label may also be used when the lifecycle label is `resume:failed`,
provided the existing Pull Request is still open.

The runner regenerates the stable issue output, force-updates the existing
`resume/<issue-number>` branch with `--force-with-lease`, and keeps the existing
Pull Request. A regeneration request without exactly one open Pull Request is
failed safely, regardless of the lifecycle label.

## Consequences

Review history stays in one Pull Request and the runner remains an independent
polling process. Regeneration intentionally replaces the generated branch state
from the current default branch, so manual changes to generated artifacts must
be reapplied after regeneration. The profile remains the source of facts, and
the action label does not introduce a second lifecycle state.
