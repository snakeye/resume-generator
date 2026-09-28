"""Parsing and validation for rendered GitHub Issue Forms."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class IssueFormError(ValueError):
    """Raised when an issue body is not a supported resume request."""


class ResumeTask(BaseModel):
    """Validated task extracted from one GitHub Issue Form response."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    form_version: Literal[1]
    issue_number: int | None = Field(default=None, ge=1)
    issue_created_at: str | None = Field(default=None, min_length=1)
    company: str = Field(min_length=1)
    position: str = Field(min_length=1)
    language: Literal["English"]
    job_description: str = Field(min_length=1)
    additional_instructions: str | None = None


_FIELD_HEADINGS = (
    ("Company", "company"),
    ("Position", "position"),
    ("Resume language", "language"),
    ("Job description", "job_description"),
    ("Additional preferences", "additional_instructions"),
    ("Form version", "form_version"),
)
_HEADING_RE = re.compile(r"^### ([^\n]+?)\s*$", re.MULTILINE)
_HEADING_NAMES = {heading for heading, _ in _FIELD_HEADINGS}


def parse_issue_body(
    body: str,
    *,
    issue_number: int | None = None,
    issue_created_at: str | None = None,
) -> ResumeTask:
    """Parse the rendered Markdown produced by the supported Issue Form."""
    if not isinstance(body, str) or not body.strip():
        raise IssueFormError("Issue body must be a non-empty string.")

    fields = _extract_fields(body)
    values = {name: _clean_value(fields[name], name) for _, name in _FIELD_HEADINGS}
    values["form_version"] = 1
    if not values["additional_instructions"]:
        values["additional_instructions"] = None
    try:
        return ResumeTask(
            **values,
            issue_number=issue_number,
            issue_created_at=issue_created_at,
        )
    except ValidationError as error:
        first = error.errors()[0]
        path = ".".join(str(part) for part in first["loc"]) or "task"
        raise IssueFormError(f"Issue form field {path}: {first['msg']}") from error


def format_issue_title(company: str, position: str, created_at: str) -> str:
    """Build the stable title shown for a generated resume request."""
    try:
        issue_date = datetime.fromisoformat(created_at.replace("Z", "+00:00")).date().isoformat()
    except (AttributeError, ValueError) as error:
        raise IssueFormError(f"Invalid GitHub issue creation date: {created_at}") from error
    return f"[Resume] {company} — {position} — {issue_date}"


def _extract_fields(body: str) -> dict[str, str]:
    headings = list(_HEADING_RE.finditer(body))
    expected = [heading for heading, _ in _FIELD_HEADINGS]
    positions: list[tuple[str, int, int]] = []
    search_from = 0

    for heading in expected:
        match = next(
            (candidate for candidate in headings if candidate.start() >= search_from and candidate.group(1) == heading),
            None,
        )
        if match is None:
            raise IssueFormError(f"Issue form is missing the '{heading}' field.")
        positions.append((heading, match.start(), match.end()))
        search_from = match.end()

    recognized = [heading.group(1) for heading in headings if heading.group(1) in _HEADING_NAMES]
    if recognized != expected:
        raise IssueFormError("Issue form fields are duplicated or out of order.")

    fields: dict[str, str] = {}
    for index, (_, _, end) in enumerate(positions):
        next_start = positions[index + 1][1] if index + 1 < len(positions) else len(body)
        fields[_FIELD_HEADINGS[index][1]] = body[end:next_start]
    return fields


def _clean_value(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned and field_name != "additional_instructions":
        raise IssueFormError(f"Issue form field '{field_name}' must not be empty.")
    if field_name == "form_version" and cleaned != "1":
        raise IssueFormError("Unsupported issue form version; expected 1.")
    return cleaned
