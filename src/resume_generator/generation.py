"""Configured domain pipeline and publishable resume artifacts."""

from __future__ import annotations

import importlib.metadata
import json
import platform
import re
import shutil
import unicodedata
from collections.abc import Callable
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

from .assembly import assemble_resume
from .bullets import generate_bullets
from .evidence import calculate_coverage, match_evidence, match_profile_evidence
from .headline import generate_headline
from .issue import ResumeTask
from .pipeline import PipelineResult, ResumeRequest, RunContext, StageProgress, run_pipeline, sha256_json
from .profile import load_profile
from .provider import LLMProvider
from .rendering import (
    Compiler,
    PdfExtractor,
    expected_rendered_text,
    render_docx,
    render_markdown,
    render_resume,
    validate_docx,
    validate_pdf,
)
from .selection import select_facts
from .skills import select_skills
from .summary import generate_summary
from .terminology import normalize_terminology
from .vacancy import analyze_vacancy
from .validation import validate_resume
from .voice import adapt_voice


class GenerationError(RuntimeError):
    """Raised when a generated resume cannot become a publishable artifact."""


PUBLISHABLE_FILES = (
    "resume.json",
    "resume.md",
    "resume.tex",
    "resume.pdf",
    "resume.docx",
    "report.md",
    "run-metadata.json",
)


class ResumePipeline:
    """Run all domain stages and write the exact output artifact set."""

    def __init__(
        self,
        *,
        root: Path,
        provider: LLMProvider,
        compiler: Compiler | None = None,
        pdf_extractor: PdfExtractor | None = None,
        pdf_validator: Callable[..., tuple[str, ...]] = validate_pdf,
        on_stage: StageProgress | None = None,
    ) -> None:
        self.root = root
        self.provider = provider
        self.compiler = compiler
        self.pdf_extractor = pdf_extractor
        self.pdf_validator = pdf_validator
        self.on_stage = on_stage

    def run(self, task: ResumeTask) -> PipelineResult:
        profile = load_profile(self.root / "data/profile/profile.yaml")
        run_id = _run_id(task)
        state: dict[str, Any] = {"profile": profile, "provider": self.provider}
        stages = self._stages(state, task)
        request = ResumeRequest(
            company=task.company,
            position=task.position,
            language=task.language,
            job_description=task.job_description,
            additional_instructions=task.additional_instructions,
        )
        metadata = _reproducibility_metadata(profile, task, self.provider)
        result = run_pipeline(
            request,
            root=self.root,
            run_id=run_id,
            stages=stages,
            on_run_created=lambda context: _configure_debug_directory(self.provider, context.debug_dir),
            on_stage=self.on_stage,
            metadata=metadata,
        )
        if not result.success:
            return result
        try:
            output_directory = _publishable_output(self.root, task, result.output_directory, state)
        except (GenerationError, OSError, ValueError) as error:
            return PipelineResult(success=False, output_directory=result.output_directory, error=str(error))
        return PipelineResult(success=True, output_directory=output_directory)

    def _stages(
        self, state: dict[str, Any], task: ResumeTask
    ) -> dict[str, Callable[[Any, RunContext], dict[str, Any]]]:
        return {
            "10-input": lambda _request, _context: {
                "company": task.company,
                "position": task.position,
                "language": task.language,
                "job_description": task.job_description,
                "additional_instructions": task.additional_instructions,
            },
            "20-vacancy": lambda _request, _context: _run_vacancy(state, task, self.provider),
            "30-terminology": lambda _request, _context: _run_terminology(state),
            "40-evidence": lambda _request, _context: _run_evidence(state, self.provider),
            "50-selection": lambda _request, _context: _run_selection(state, self.provider),
            "60-writing": lambda _request, _context: _run_writing(state, self.provider),
            "70-skills": lambda _request, _context: _run_skills(state),
            "80-voice": lambda _request, _context: _run_voice(state, self.provider),
            "90-assembly": lambda _request, _context: _run_assembly(state),
            "100-validation": lambda _request, _context: _run_validation(state),
            "110-rendering": lambda _request, context: _run_rendering(state, context, self.compiler),
            "120-pdf-validation": lambda _request, _context: _run_pdf_validation(
                state, self.pdf_validator, self.pdf_extractor
            ),
        }


def _run_vacancy(state: dict[str, Any], task: ResumeTask, provider: LLMProvider) -> dict[str, Any]:
    state["vacancy"] = analyze_vacancy(task, provider)
    return state["vacancy"].model_dump(mode="json")


def _run_terminology(state: dict[str, Any]) -> dict[str, Any]:
    state["terminology"] = normalize_terminology(state["profile"], state["vacancy"])
    return state["terminology"].model_dump(mode="json")


def _run_evidence(state: dict[str, Any], provider: LLMProvider) -> dict[str, Any]:
    matchings = tuple(
        match_evidence(state["vacancy"], work, work_index=index, provider=provider)
        for index, work in enumerate(state["profile"].work)
    )
    matchings = (*matchings, match_profile_evidence(state["vacancy"], state["profile"], provider=provider))
    state["matchings"] = matchings
    state["coverage"] = calculate_coverage(state["vacancy"], matchings)
    return {
        "matchings": [matching.model_dump(mode="json") for matching in matchings],
        "coverage": state["coverage"].model_dump(mode="json"),
    }


def _run_selection(state: dict[str, Any], provider: LLMProvider) -> dict[str, Any]:
    state["selection"] = select_facts(state["vacancy"], state["profile"], state["matchings"], provider)
    return state["selection"].model_dump(mode="json")


def _run_writing(state: dict[str, Any], provider: LLMProvider) -> dict[str, Any]:
    headline = generate_headline(state["vacancy"], state["profile"], state["selection"], provider)
    bullets = generate_bullets(state["vacancy"], state["terminology"], state["profile"], state["selection"], provider)
    summary = generate_summary(state["vacancy"], state["profile"], state["selection"], provider)
    state.update(headline=headline, bullets=bullets, summary=summary)
    return {
        "headline": headline.model_dump(mode="json"),
        "bullets": bullets.model_dump(mode="json"),
        "summary": summary.model_dump(mode="json"),
    }


def _run_skills(state: dict[str, Any]) -> dict[str, Any]:
    state["skills"] = select_skills(state["terminology"])
    return state["skills"].model_dump(mode="json")


def _run_voice(state: dict[str, Any], provider: LLMProvider) -> dict[str, Any]:
    state["voice"] = adapt_voice(state["profile"], state["terminology"], state["summary"], state["bullets"], provider)
    return state["voice"].model_dump(mode="json")


def _run_assembly(state: dict[str, Any]) -> dict[str, Any]:
    state["resume"] = assemble_resume(state["profile"], state["headline"], state["voice"], state["skills"])
    return state["resume"].model_dump(mode="json")


def _run_validation(state: dict[str, Any]) -> dict[str, Any]:
    covered = frozenset(
        requirement.id
        for requirement in state["vacancy"].requirements
        if requirement.priority != "context"
        if requirement.id not in state["selection"].uncovered
    )
    state["validation"] = validate_resume(
        state["profile"], state["resume"], vacancy=state["vacancy"], covered_requirements=covered
    )
    if not state["validation"].valid:
        errors = "; ".join(issue.message for issue in state["validation"].issues if issue.severity == "error")
        raise GenerationError(f"Resume validation failed: {errors}")
    return state["validation"].model_dump(mode="json")


def _run_rendering(state: dict[str, Any], context: RunContext, compiler: Compiler | None) -> dict[str, Any]:
    tex_path, pdf_path = render_resume(state["resume"], context.run_dir, compiler=compiler)
    markdown_path = render_markdown(state["resume"], context.run_dir)
    docx_path = render_docx(state["resume"], context.run_dir)
    state["tex_path"] = tex_path
    state["pdf_path"] = pdf_path
    state["markdown_path"] = markdown_path
    state["docx_path"] = docx_path
    return {
        "markdown": str(markdown_path.relative_to(context.run_dir)),
        "tex": str(tex_path.relative_to(context.run_dir)),
        "pdf": str(pdf_path.relative_to(context.run_dir)),
        "docx": str(docx_path.relative_to(context.run_dir)),
    }


def _run_pdf_validation(
    state: dict[str, Any],
    pdf_validator: Callable[..., tuple[str, ...]],
    extractor: PdfExtractor | None,
) -> dict[str, Any]:
    resume = state["resume"]
    pdf_expected = expected_rendered_text(resume, skills_heading="Skills & Core Competencies")
    issues = pdf_validator(state["pdf_path"], pdf_expected, extractor=extractor)
    if issues:
        raise GenerationError("PDF validation failed: " + "; ".join(issues))
    if "docx_path" in state:
        docx_expected = expected_rendered_text(resume, skills_heading="Skills")
        docx_issues = validate_docx(state["docx_path"], docx_expected)
        if docx_issues:
            raise GenerationError("DOCX validation failed: " + "; ".join(docx_issues))
    return {"valid": True, "issues": []}


def _publishable_output(root: Path, task: ResumeTask, run_directory: Path, state: dict[str, Any]) -> Path:
    output_directory = publishable_output_directory(root, task)
    output_directory.mkdir(parents=True, exist_ok=True)
    unexpected = [path.name for path in output_directory.iterdir() if path.name not in PUBLISHABLE_FILES]
    if unexpected:
        raise GenerationError(f"Output directory contains unexpected files: {', '.join(sorted(unexpected))}")
    _write_json(output_directory / "resume.json", state["resume"].model_dump(mode="json"))
    shutil.copyfile(state["markdown_path"], output_directory / "resume.md")
    shutil.copyfile(state["tex_path"], output_directory / "resume.tex")
    shutil.copyfile(state["pdf_path"], output_directory / "resume.pdf")
    shutil.copyfile(state["docx_path"], output_directory / "resume.docx")
    report = _report(state, task)
    (run_directory / "report.md").write_text(report, encoding="utf-8")
    (output_directory / "report.md").write_text(report, encoding="utf-8")
    metadata = json.loads((run_directory / "run-metadata.json").read_text(encoding="utf-8"))
    metadata.update({"issue_number": task.issue_number, "provider": _provider_metadata(state)})
    _write_json(output_directory / "run-metadata.json", metadata)
    return output_directory


def publishable_output_directory(root: Path, task: ResumeTask) -> Path:
    """Return the stable, human-readable directory for one issue's artifacts."""
    issue_date = _issue_date(task.issue_created_at)
    identity = "-".join((_slug(task.company), _slug(task.position)))
    issue_name = f"{task.issue_number or 'local'}-{identity}"
    return root / "data" / "output" / issue_date / issue_name


def _issue_date(created_at: str) -> str:
    if not created_at:
        raise ValueError("GitHub issue creation date is required for publishable output.")
    try:
        return datetime.fromisoformat(created_at.replace("Z", "+00:00")).date().isoformat()
    except ValueError as error:
        raise ValueError(f"Invalid GitHub issue creation date: {created_at}") from error


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return slug or "unknown"


def _report(state: dict[str, Any], task: ResumeTask) -> str:
    candidate_requirements = tuple(
        requirement for requirement in state["vacancy"].requirements if requirement.priority != "context"
    )
    evidence_by_requirement: dict[str, dict[str, str]] = {requirement.id: {} for requirement in candidate_requirements}
    for matching in state["matchings"]:
        for match in matching.matches:
            evidence = evidence_by_requirement[match.requirement_id]
            for path in match.source_paths:
                if evidence.get(path) != "strong":
                    evidence[path] = match.strength
    selected_by_requirement: dict[str, list[str]] = {requirement.id: [] for requirement in candidate_requirements}
    supplemental_facts: list[str] = []
    for selected in state["selection"].selected:
        if not selected.covers:
            supplemental_facts.append(selected.fact_path)
        for requirement_id in selected.covers:
            selected_by_requirement[requirement_id].append(selected.fact_path)
    final_fact_paths = _resume_fact_paths(state["resume"])
    represented = {
        requirement.id
        for requirement in candidate_requirements
        if _requirement_is_represented(
            evidence_by_requirement[requirement.id],
            selected_by_requirement[requirement.id],
            final_fact_paths,
        )
    }
    gaps = tuple(requirement for requirement in candidate_requirements if not evidence_by_requirement[requirement.id])
    weak = tuple(
        requirement
        for requirement in candidate_requirements
        if evidence_by_requirement[requirement.id]
        and set(evidence_by_requirement[requirement.id].values()) == {"partial"}
    )
    weak_ids = {requirement.id for requirement in weak}
    omitted = tuple(
        requirement
        for requirement in candidate_requirements
        if evidence_by_requirement[requirement.id]
        and requirement.id not in represented
        and requirement.id not in weak_ids
    )
    contexts = tuple(requirement for requirement in state["vacancy"].requirements if requirement.priority == "context")
    warnings = tuple(
        issue
        for issue in state["validation"].issues
        if issue.severity == "warning" and issue.code != "coverage.uncovered"
    )
    lines = [
        "# Profile gap report",
        "",
        f"Company: {_markdown_text(task.company)}",
        f"Position: {_markdown_text(task.position)}",
        "",
        "## Summary",
        "",
        "| Priority | Profile evidence | Represented in CV |",
        "| --- | ---: | ---: |",
        *_coverage_summary(candidate_requirements, evidence_by_requirement, represented),
        "",
        "## Profile gaps",
        "",
        "These requirements have no supporting evidence in the profile.",
        "",
        *_gap_lines(gaps),
        "",
        *_optional_requirement_section(
            "Evidence to strengthen",
            "These requirements have only partial evidence. The experience may exist, but the profile does not "
            "describe it explicitly enough.",
            weak,
            evidence_by_requirement,
            represented,
            state["profile"],
        ),
        *_optional_requirement_section(
            "Evidence not represented in CV",
            "Strong profile evidence exists, but the generated CV does not demonstrate these requirements.",
            omitted,
            evidence_by_requirement,
            represented,
            state["profile"],
        ),
        *_provenance_lines(
            candidate_requirements,
            evidence_by_requirement,
            represented,
            supplemental_facts,
            final_fact_paths,
            state["profile"],
        ),
        *_details_lines(
            "Vacancy context",
            tuple(f"- {_markdown_text(requirement.text)}" for requirement in contexts),
        ),
        *_details_lines("CV quality warnings", _warning_lines(warnings)),
        "",
        "Generation metadata: [run-metadata.json](run-metadata.json)",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _coverage_summary(
    requirements: tuple[Any, ...], evidence: dict[str, dict[str, str]], represented: set[str]
) -> tuple[str, ...]:
    labels = {"must_have": "Must have", "important": "Important", "nice_to_have": "Nice to have"}
    lines = []
    for priority, label in labels.items():
        items = tuple(requirement for requirement in requirements if requirement.priority == priority)
        if not items:
            continue
        covered = sum(bool(evidence[requirement.id]) for requirement in items)
        in_cv = sum(requirement.id in represented for requirement in items)
        lines.append(f"| {label} | {covered}/{len(items)} | {in_cv}/{len(items)} |")
    return tuple(lines)


def _gap_lines(requirements: tuple[Any, ...]) -> tuple[str, ...]:
    if not requirements:
        return ("No profile gaps found.",)
    return tuple(
        line
        for requirement in requirements
        for line in (
            f"- **{requirement.id} ({_priority_label(requirement.priority)}):** {_markdown_text(requirement.text)}",
            "  Next action: if this is true, add concrete evidence to the relevant profile section.",
        )
    )


def _optional_requirement_section(
    title: str,
    introduction: str,
    requirements: tuple[Any, ...],
    evidence: dict[str, dict[str, str]],
    represented: set[str],
    profile: Any,
) -> tuple[str, ...]:
    if not requirements:
        return ()
    return (
        f"## {title}",
        "",
        introduction,
        "",
        *(
            line
            for requirement in requirements
            for line in _actionable_requirement_lines(
                requirement, evidence[requirement.id], requirement.id in represented, profile
            )
        ),
        "",
    )


def _actionable_requirement_lines(
    requirement: Any, evidence: dict[str, str], represented: bool, profile: Any
) -> tuple[str, ...]:
    return (
        f"- **{requirement.id} ({_priority_label(requirement.priority)}):** {_markdown_text(requirement.text)}",
        f"  CV: {'represented' if represented else 'not represented'}.",
        *(
            f"  - `{path}` ({strength}): {_markdown_text(_excerpt(_source_text(profile, path)))}"
            for path, strength in evidence.items()
        ),
    )


def _provenance_lines(
    requirements: tuple[Any, ...],
    evidence: dict[str, dict[str, str]],
    represented: set[str],
    supplemental_facts: list[str],
    final_fact_paths: set[str],
    profile: Any,
) -> tuple[str, ...]:
    evidence_paths = tuple(dict.fromkeys(path for sources in evidence.values() for path in sources))
    lines = [
        "<details>",
        f"<summary>Full requirement provenance ({len(requirements)} requirements)</summary>",
        "",
        "### Requirement map",
        "",
    ]
    for requirement in requirements:
        sources = evidence[requirement.id]
        status = "represented in CV" if requirement.id in represented else "not represented in CV"
        strength = "strong" if "strong" in sources.values() else "partial" if sources else "none"
        lines.extend(
            (
                f"- **{requirement.id} ({_priority_label(requirement.priority)}, {strength}, {status}):** "
                f"{_markdown_text(requirement.text)}",
                "  Evidence: "
                + (", ".join(f"`{path}` ({source_strength})" for path, source_strength in sources.items()) or "none"),
            )
        )
    if evidence_paths:
        lines.extend(("", "### Evidence index", ""))
        lines.extend(
            f"- `{path}`{' [in CV]' if _source_is_in_resume(path, final_fact_paths) else ''}: "
            f"{_markdown_text(_source_text(profile, path))}"
            for path in evidence_paths
        )
    if supplemental_facts:
        lines.extend(("", "### Supplemental facts selected for CV", ""))
        lines.extend(f"- `{path}`: {_markdown_text(_source_text(profile, path))}" for path in supplemental_facts)
    lines.extend(("", "</details>", ""))
    return tuple(lines)


def _details_lines(title: str, content: tuple[str, ...]) -> tuple[str, ...]:
    if not content:
        return ()
    return (
        "<details>",
        f"<summary>{title} ({len(content)})</summary>",
        "",
        *content,
        "",
        "</details>",
        "",
    )


def _warning_lines(warnings: tuple[Any, ...]) -> tuple[str, ...]:
    return tuple(
        f"- `{issue.code}`" + (f" at `{issue.path}`" if issue.path else "") + f": {_markdown_text(issue.message)}"
        for issue in warnings
    )


def _requirement_is_represented(evidence: dict[str, str], selected: list[str], final_fact_paths: set[str]) -> bool:
    return any(path in final_fact_paths for path in selected) or any(
        not re.fullmatch(r"work\[\d+\]\.facts\[\d+\]", path) for path in evidence
    )


def _source_is_in_resume(path: str, final_fact_paths: set[str]) -> bool:
    return path in final_fact_paths or not re.fullmatch(r"work\[\d+\]\.facts\[\d+\]", path)


def _priority_label(priority: str) -> str:
    return priority.replace("_", " ")


def _excerpt(text: str, limit: int = 160) -> str:
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _markdown_text(text: str) -> str:
    text = " ".join(text.split())
    text = text.replace("\\", "\\\\")
    for character in ("`", "*", "_", "[", "]"):
        text = text.replace(character, f"\\{character}")
    return text.replace("<", "&lt;").replace(">", "&gt;")


def _resume_fact_paths(resume: Any) -> set[str]:
    paths = set(resume.headline.fact_paths) | set(resume.summary.fact_paths)
    for company in resume.experience:
        for role in company.roles:
            for bullet in role.bullets:
                paths.update(bullet.fact_paths)
    if resume.earlier_experience is not None:
        for bullet in resume.earlier_experience.bullets:
            paths.update(bullet.fact_paths)
    return paths


def _source_text(profile: Any, fact_path: str) -> str:
    language = re.fullmatch(r"languages\[(\d+)\]", fact_path)
    if language is not None:
        item = profile.languages[int(language[1])]
        return f"{item.language}: {item.level}"
    education = re.fullmatch(r"education\[(\d+)\]", fact_path)
    if education is not None:
        item = profile.education[int(education[1])]
        return ", ".join(part for part in (item.study_type, item.area, item.institution) if part)
    match = re.fullmatch(r"work\[(\d+)\]\.facts\[(\d+)\]", fact_path)
    if match is not None:
        return " ".join(profile.work[int(match[1])].facts[int(match[2])].text.split())
    skill = re.fullmatch(r"work\[(\d+)\]\.skills\[(\d+)\]", fact_path)
    if skill is not None:
        return profile.work[int(skill[1])].skills[int(skill[2])]
    return "unknown fact"


def _provider_metadata(state: dict[str, Any]) -> dict[str, str]:
    provider = state.get("provider")
    if provider is None:
        return {}
    return {key: str(getattr(provider, key)) for key in ("provider_name", "model") if hasattr(provider, key)}


def _reproducibility_metadata(profile: Any, task: ResumeTask, provider: LLMProvider) -> dict[str, Any]:
    provider_config = _provider_configuration(provider)
    prompt_versions = _prompt_versions()
    return {
        "issue_sha256": sha256_json(task.model_dump(mode="json")),
        "profile_sha256": sha256_json(profile.model_dump(mode="json")),
        "configuration_sha256": sha256_json(provider_config),
        "prompt_sha256": prompt_versions["bundle_sha256"],
        "prompt_versions": prompt_versions["files"],
        "schema_versions": {
            "issue_form": task.form_version,
            "profile": profile.schema_version,
            "stage_artifact": 1,
        },
        "contract_versions": {"resume_request": 1},
        "provider": _provider_metadata({"provider": provider}),
        "toolchain_versions": _toolchain_versions(),
    }


def _provider_configuration(provider: LLMProvider) -> dict[str, str]:
    keys = ("provider_name", "model", "endpoint", "timeout", "retries")
    return {key: str(getattr(provider, key)) for key in keys if hasattr(provider, key)}


def _prompt_versions() -> dict[str, Any]:
    root = resources.files("resume_generator.resources").joinpath("prompts")
    files: dict[str, str] = {}

    def collect(directory: Any, prefix: str = "") -> None:
        for entry in sorted(directory.iterdir(), key=lambda item: item.name):
            relative = f"{prefix}/{entry.name}" if prefix else entry.name
            if entry.is_dir():
                collect(entry, relative)
            elif entry.is_file() and entry.name.endswith(".md"):
                files[relative] = sha256_json(entry.read_text(encoding="utf-8"))

    collect(root)
    return {"bundle_sha256": sha256_json(files), "files": files}


def _toolchain_versions() -> dict[str, str]:
    versions = {"python": platform.python_version()}
    for distribution in ("resume-generator", "pydantic", "pydantic-settings", "Jinja2", "python-docx", "PyYAML"):
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            continue
    return versions


def _configure_debug_directory(provider: LLMProvider, directory: Path) -> None:
    configure = getattr(provider, "set_debug_directory", None)
    if callable(configure):
        configure(directory)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run_id(task: ResumeTask) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    return f"issue-{task.issue_number or 'unknown'}-{timestamp}"
