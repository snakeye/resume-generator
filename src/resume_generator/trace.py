"""Compact console progress reporting for local resume runs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .pipeline import PIPELINE_STAGE_NAMES


class ConsoleTracer:
    """Render useful pipeline and runner events without exposing input data."""

    def __init__(self, *, quiet: bool = False, debug: bool = False, output: Any = print) -> None:
        self.quiet = quiet
        self.debug = debug
        self.output = output

    def message(self, text: str) -> None:
        if not self.quiet:
            self.output(text)

    def result(self, text: str) -> None:
        self.output(text)

    def stage(self, status: str, stage_name: str, payload: Mapping[str, Any] | None, elapsed: float | None) -> None:
        if self.quiet:
            return
        if status == "started":
            stage_number = PIPELINE_STAGE_NAMES.index(stage_name) + 1
            self.output(f"[{stage_number}/{len(PIPELINE_STAGE_NAMES)}] {_stage_title(stage_name)}...")
            return
        if status == "failed":
            self.output(f"       FAILED: {_stage_title(stage_name)}")
            return

        summary = _stage_summary(stage_name, payload or {})
        suffix = f" ({elapsed:.1f}s)" if self.debug and elapsed is not None else ""
        self.output(f"       {summary}{suffix}")


def _stage_title(stage_name: str) -> str:
    titles = {
        "10-input": "Storing request",
        "20-vacancy": "Analyzing vacancy",
        "30-terminology": "Normalizing terminology",
        "40-evidence": "Matching evidence",
        "50-selection": "Selecting facts",
        "60-writing": "Writing resume content",
        "70-skills": "Selecting skills",
        "80-voice": "Applying voice profile",
        "90-assembly": "Assembling resume",
        "100-validation": "Validating resume",
        "110-rendering": "Rendering resume formats",
        "120-pdf-validation": "Validating PDF",
    }
    return titles.get(stage_name, stage_name)


def _stage_summary(stage_name: str, payload: Mapping[str, Any]) -> str:  # noqa: C901 - explicit stage summaries stay readable
    if stage_name == "10-input":
        return "Request stored"
    if stage_name == "20-vacancy":
        requirements = payload.get("requirements", [])
        counts = {priority: 0 for priority in ("must_have", "important", "nice_to_have", "context")}
        for requirement in requirements:
            if isinstance(requirement, Mapping) and requirement.get("priority") in counts:
                counts[requirement["priority"]] += 1
        return f"{len(requirements)} requirements: " + ", ".join(
            f"{count} {priority.replace('_', '-')}" for priority, count in counts.items() if count
        )
    if stage_name == "30-terminology":
        return f"{_count_payload_values(payload)} terminology groups normalized"
    if stage_name == "40-evidence":
        matchings = payload.get("matchings", [])
        matches = sum(len(item.get("matches", [])) for item in matchings if isinstance(item, Mapping))
        coverage = payload.get("coverage", {}).get("items", []) if isinstance(payload.get("coverage"), Mapping) else []
        covered = sum(item.get("status") == "covered" for item in coverage if isinstance(item, Mapping))
        return f"{matches} matches, {covered}/{len(coverage)} requirements covered"
    if stage_name == "50-selection":
        return f"{len(payload.get('selected', []))} facts selected, {len(payload.get('uncovered', []))} uncovered"
    if stage_name == "60-writing":
        bullets = payload.get("bullets", {}).get("bullets", [])
        return f"Headline, summary, and {len(bullets)} bullets generated"
    if stage_name == "70-skills":
        return f"{_count_payload_values(payload)} skill groups selected"
    if stage_name == "80-voice":
        return "Voice adaptation completed"
    if stage_name == "90-assembly":
        return "Resume assembled"
    if stage_name == "100-validation":
        issues = payload.get("issues", [])
        warnings = sum(item.get("severity") == "warning" for item in issues if isinstance(item, Mapping))
        return f"Validation passed with {warnings} warning(s)"
    if stage_name == "110-rendering":
        return f"PDF and editable formats written: {payload.get('pdf', 'unknown path')}"
    if stage_name == "120-pdf-validation":
        return "PDF validation passed"
    return "Stage completed"


def _count_payload_values(payload: Mapping[str, Any]) -> int:
    return sum(len(value) for value in payload.values() if isinstance(value, (list, tuple, dict)))
