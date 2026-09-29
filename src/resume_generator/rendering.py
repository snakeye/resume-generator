"""Versioned resume rendering boundaries."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from collections.abc import Sequence
from importlib import resources
from pathlib import Path
from typing import Protocol

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt
from jinja2 import DictLoader, Environment, StrictUndefined

from .assembly import ResumeDocument


class RenderingError(RuntimeError):
    """Raised when TeX or PDF rendering cannot produce a safe artifact."""


class Compiler(Protocol):
    def __call__(self, tex_path: Path, output_dir: Path) -> Path: ...


class PdfExtractor(Protocol):
    def __call__(self, pdf_path: Path) -> str: ...


def render_resume(
    resume: ResumeDocument,
    output_dir: Path,
    *,
    compiler: Compiler | None = None,
) -> tuple[Path, Path]:
    """Write reviewable TeX and compile it into a PDF."""
    output_dir.mkdir(parents=True, exist_ok=True)
    tex_path = output_dir / "resume.tex"
    pdf_path = output_dir / "resume.pdf"
    tex_path.write_text(render_latex(resume), encoding="utf-8")
    produced_pdf = (compiler or compile_pdf)(tex_path, output_dir)
    if produced_pdf != pdf_path:
        shutil.copyfile(produced_pdf, pdf_path)
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise RenderingError("PDF compiler produced an empty or missing resume.pdf")
    return tex_path, pdf_path


def render_markdown(resume: ResumeDocument, output_dir: Path) -> Path:
    """Write a readable Markdown rendering of the canonical resume."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "resume.md"
    path.write_text(_render_markdown(resume), encoding="utf-8")
    return path


def render_docx(resume: ResumeDocument, output_dir: Path) -> Path:
    """Write an editable DOCX rendering of the canonical resume."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "resume.docx"
    document = Document()
    _configure_docx(document)

    name = document.add_heading(resume.basics.name, level=0)
    name.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_docx_paragraph(document, resume.headline.text, bold=True)
    _add_docx_paragraph(document, _docx_contact_line(resume), alignment=WD_ALIGN_PARAGRAPH.CENTER)
    document.add_heading("Summary", level=1)
    _add_docx_paragraph(document, resume.summary.text)
    _add_docx_skills(document, resume)
    _add_docx_experience(document, resume)
    _add_docx_education(document, resume)
    _add_docx_languages(document, resume)

    try:
        document.save(path)
    except OSError as error:
        raise RenderingError(f"Cannot write DOCX resume: {error}") from error
    if not path.exists() or path.stat().st_size == 0:
        raise RenderingError("DOCX renderer produced an empty or missing resume.docx")
    return path


def validate_docx(docx_path: Path, expected_text: Sequence[str]) -> tuple[str, ...]:
    """Check that a DOCX is readable and contains required resume text."""
    if not docx_path.exists() or docx_path.stat().st_size == 0:
        return ("DOCX is missing or empty.",)
    try:
        document = Document(docx_path)
    except Exception as error:  # noqa: BLE001 - parser errors are validation results
        return (f"DOCX cannot be read: {error}",)
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    return tuple(f"DOCX is missing expected text: {value}" for value in expected_text if value not in text)


def expected_rendered_text(resume: ResumeDocument, *, skills_heading: str) -> tuple[str, ...]:
    """Return content that every rendered resume must preserve."""
    expected = [
        resume.basics.name,
        resume.headline.text,
        resume.summary.text,
        "Summary",
        "Experience",
        *(value for value in (resume.basics.email, resume.basics.phone, resume.basics.location) if value),
        *(link.label for link in resume.basics.links),
        *(link.url for link in resume.basics.links),
    ]
    if resume.skills.skills:
        expected.append(skills_heading)
        expected.extend(skill.name for skill in resume.skills.skills)
    expected.extend(_expected_experience_text(resume))
    if resume.earlier_experience is not None:
        expected.extend(_expected_earlier_text(resume))
    if resume.education:
        expected.extend(_expected_education_text(resume))
    if resume.languages:
        expected.extend(_expected_language_text(resume))
    return tuple(value for value in expected if value)


def _expected_experience_text(resume: ResumeDocument) -> list[str]:
    expected: list[str] = []
    for company in resume.experience:
        expected.append(company.company)
        for role in company.roles:
            expected.extend((role.position, role.start_date, role.end_date or "Present"))
            expected.extend(bullet.text for bullet in role.bullets)
            expected.extend(role.tech_stack)
    return expected


def _expected_earlier_text(resume: ResumeDocument) -> list[str]:
    block = resume.earlier_experience
    assert block is not None
    return [
        "Earlier Experience",
        block.position,
        block.start_date,
        block.end_date,
        *(bullet.text for bullet in block.bullets),
        *block.tech_stack,
    ]


def _expected_education_text(resume: ResumeDocument) -> list[str]:
    expected = ["Education"]
    for item in resume.education:
        expected.extend((item.institution, item.degree_line, *item.details))
    return expected


def _expected_language_text(resume: ResumeDocument) -> list[str]:
    expected = ["Languages"]
    for item in resume.languages:
        expected.extend((item.language, item.level))
    return expected


def _render_markdown(resume: ResumeDocument) -> str:
    lines = [
        f"# {_markdown(resume.basics.name)}",
        f"**{_markdown(resume.headline.text)}**",
        _contact_line(resume),
        "",
        "## Summary",
        _markdown(resume.summary.text),
        "",
    ]
    lines.extend(_markdown_skills(resume))
    lines.extend(_markdown_experience(resume))
    lines.extend(_markdown_education(resume))
    lines.extend(_markdown_languages(resume))
    return "\n".join(lines).rstrip() + "\n"


def _markdown_skills(resume: ResumeDocument) -> list[str]:
    if not resume.skills.skills:
        return []
    grouped: dict[str, list[str]] = {}
    for skill in resume.skills.skills:
        grouped.setdefault(skill.group, []).append(skill.name)
    lines = ["## Skills", ""]
    lines.extend(
        f"- **{_markdown(group)}:** {', '.join(_markdown(skill) for skill in skills)}"
        for group, skills in grouped.items()
    )
    return [*lines, ""]


def _markdown_experience(resume: ResumeDocument) -> list[str]:
    lines = ["## Experience", ""]
    for company in resume.experience:
        lines.append(f"### {_markdown(company.company)}{_location(company.location)}")
        for role in company.roles:
            lines.append(f"**{_markdown(role.position)}** | {_date_range(role.start_date, role.end_date)}")
            lines.extend(f"- {_markdown(bullet.text)}" for bullet in role.bullets)
            if role.tech_stack:
                lines.append(f"_Technologies:_ {', '.join(_markdown(skill) for skill in role.tech_stack)}")
            lines.append("")
    if resume.earlier_experience is not None:
        block = resume.earlier_experience
        lines.extend(
            (
                "### Earlier Experience",
                f"**{_markdown(block.position)}** | {_date_range(block.start_date, block.end_date)}",
            )
        )
        lines.extend(f"- {_markdown(bullet.text)}" for bullet in block.bullets)
        if block.tech_stack:
            lines.append(f"_Technologies:_ {', '.join(_markdown(skill) for skill in block.tech_stack)}")
        lines.append("")
    return lines


def _markdown_education(resume: ResumeDocument) -> list[str]:
    if not resume.education:
        return []
    lines = ["## Education", ""]
    for item in resume.education:
        line = " - ".join(part for part in (item.institution, item.degree_line) if part)
        if item.start_date or item.end_date:
            line = f"{line} | {_date_range(item.start_date or '', item.end_date)}"
        lines.append(f"- {_markdown(line)}")
        lines.extend(f"  - {_markdown(detail)}" for detail in item.details)
    return [*lines, ""]


def _markdown_languages(resume: ResumeDocument) -> list[str]:
    if not resume.languages:
        return []
    return [
        "## Languages",
        "",
        *(f"- {_markdown(item.language)}: {_markdown(item.level)}" for item in resume.languages),
        "",
    ]


def _contact_line(resume: ResumeDocument) -> str:
    values = [resume.basics.email, resume.basics.phone, resume.basics.location]
    values.extend(f"[{link.label}]({link.url})" for link in resume.basics.links)
    return " | ".join(_markdown(value) if not value.startswith("[") else value for value in values if value)


def _docx_contact_line(resume: ResumeDocument) -> str:
    values = [resume.basics.email, resume.basics.phone, resume.basics.location]
    values.extend(f"{link.label}: {link.url}" for link in resume.basics.links)
    return " | ".join(value for value in values if value)


def _markdown(value: str) -> str:
    """Escape user-controlled text that could become Markdown structure."""
    escaped = value.replace("\\", "\\\\")
    for character in ("*", "_", "[", "]", "<", ">", "`", "#"):
        escaped = escaped.replace(character, f"\\{character}")
    return escaped


def _location(location: str | None) -> str:
    return f" ({_markdown(location)})" if location else ""


def _date_range(start_date: str, end_date: str | None) -> str:
    return f"{_markdown(start_date)} - {_markdown(end_date or 'Present')}"


def _plain_date_range(start_date: str, end_date: str | None) -> str:
    return f"{start_date} - {end_date or 'Present'}"


def _configure_docx(document: Document) -> None:
    section = document.sections[0]
    section.top_margin = section.bottom_margin = section.left_margin = section.right_margin = Inches(0.7)
    document.styles["Normal"].font.name = "Aptos"
    document.styles["Normal"].font.size = Pt(10)


def _add_docx_paragraph(document: Document, text: str, *, bold: bool = False, alignment=None) -> None:
    paragraph = document.add_paragraph()
    if alignment is not None:
        paragraph.alignment = alignment
    run = paragraph.add_run(text)
    run.bold = bold


def _add_docx_skills(document: Document, resume: ResumeDocument) -> None:
    if not resume.skills.skills:
        return
    document.add_heading("Skills", level=1)
    grouped: dict[str, list[str]] = {}
    for skill in resume.skills.skills:
        grouped.setdefault(skill.group, []).append(skill.name)
    for group, skills in grouped.items():
        _add_docx_paragraph(document, f"{group}: {', '.join(skills)}")


def _add_docx_experience(document: Document, resume: ResumeDocument) -> None:
    document.add_heading("Experience", level=1)
    for company in resume.experience:
        document.add_heading(company.company, level=2)
        for role in company.roles:
            _add_docx_paragraph(
                document, f"{role.position} | {_plain_date_range(role.start_date, role.end_date)}", bold=True
            )
            for bullet in role.bullets:
                document.add_paragraph(bullet.text, style="List Bullet")
            if role.tech_stack:
                _add_docx_paragraph(document, f"Technologies: {', '.join(role.tech_stack)}")
    if resume.earlier_experience is None:
        return
    block = resume.earlier_experience
    document.add_heading("Earlier Experience", level=2)
    _add_docx_paragraph(
        document, f"{block.position} | {_plain_date_range(block.start_date, block.end_date)}", bold=True
    )
    for bullet in block.bullets:
        document.add_paragraph(bullet.text, style="List Bullet")
    if block.tech_stack:
        _add_docx_paragraph(document, f"Technologies: {', '.join(block.tech_stack)}")


def _add_docx_education(document: Document, resume: ResumeDocument) -> None:
    if not resume.education:
        return
    document.add_heading("Education", level=1)
    for item in resume.education:
        line = " - ".join(part for part in (item.institution, item.degree_line) if part)
        if item.start_date or item.end_date:
            line = f"{line} | {_plain_date_range(item.start_date or '', item.end_date)}"
        _add_docx_paragraph(document, line)
        for detail in item.details:
            document.add_paragraph(detail, style="List Bullet")


def _add_docx_languages(document: Document, resume: ResumeDocument) -> None:
    if not resume.languages:
        return
    document.add_heading("Languages", level=1)
    for item in resume.languages:
        _add_docx_paragraph(document, f"{item.language}: {item.level}")


def render_latex(resume: ResumeDocument) -> str:
    """Render the canonical resume through the versioned application template."""
    template_root = resources.files("resume_generator.resources").joinpath("templates")
    template = template_root.joinpath("resume-v2.tex").read_text(encoding="utf-8")
    font_setup = template_root.joinpath("font_setup.tex").read_text(encoding="utf-8")
    skill_groups = _render_skill_groups(resume)
    values = {
        "name": _latex(resume.basics.name),
        "email": _latex(resume.basics.email),
        "phone": _latex(resume.basics.phone or ""),
        "location": _latex(resume.basics.location or ""),
        "links": " \\textbar{} ".join(
            rf"{_latex(link.label)}: \href{{{_latex_url(link.url)}}}{{{_latex(link.url)}}}"
            for link in resume.basics.links
        ),
        "headline": _latex(resume.headline.text),
        "summary": _latex(resume.summary.text),
        "skill_groups": skill_groups,
        "experience": _render_experience(resume),
        "earlier_experience": _render_earlier_experience(resume),
        "education": _render_education(resume),
        "languages": tuple(
            {"language": _latex(item.language), "level": _latex(item.level)} for item in resume.languages
        ),
        "fonts": {
            "main": _latex(_font_value("PDF_MAIN_FONT", "Inter")),
            "fallback": _latex(_font_value("PDF_FALLBACK_FONT", "Noto Sans")),
        },
    }
    environment = Environment(
        loader=DictLoader({"resume-v2.tex": template, "font_setup.tex": font_setup}),
        undefined=StrictUndefined,
        autoescape=False,
        variable_start_string="<<",
        variable_end_string=">>",
        comment_start_string="{#@",
        comment_end_string="@#}",
    )
    return environment.get_template("resume-v2.tex").render(**values)


def compile_pdf(tex_path: Path, output_dir: Path, *, timeout: float = 60.0) -> Path:
    """Compile TeX with the locally installed deterministic compiler."""
    command = shutil.which("xelatex")
    if command is None:
        raise RenderingError("xelatex is not installed. Install the PDF toolchain and rerun rendering.")
    with tempfile.TemporaryDirectory(prefix="resume-render-") as temporary:
        temporary_dir = Path(temporary)
        try:
            result = None
            for _ in range(2):
                result = subprocess.run(
                    [
                        command,
                        "-interaction=nonstopmode",
                        "-halt-on-error",
                        "-output-directory",
                        str(temporary_dir),
                        str(tex_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
                if result.returncode != 0:
                    break
        except subprocess.TimeoutExpired as error:
            raise RenderingError(f"LaTeX compilation timed out after {timeout:g} seconds.") from error
        if result is None or result.returncode != 0:
            diagnostic = _last_output(result.stdout, result.stderr)
            raise RenderingError(f"LaTeX compilation failed: {diagnostic}")
        compiled_pdf = temporary_dir / f"{tex_path.stem}.pdf"
        if not compiled_pdf.exists():
            raise RenderingError("LaTeX completed without producing a PDF.")
        pdf_path = output_dir / compiled_pdf.name
        shutil.copyfile(compiled_pdf, pdf_path)
    return pdf_path


def validate_pdf(
    pdf_path: Path,
    expected_text: Sequence[str],
    *,
    extractor: PdfExtractor | None = None,
) -> tuple[str, ...]:
    """Extract PDF text and return blocking validation messages."""
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        return ("PDF is missing or empty.",)
    try:
        text = (extractor or extract_pdf_text)(pdf_path)
    except RenderingError as error:
        return (str(error),)
    normalized_text = _normalize_pdf_text(text)
    return tuple(
        f"PDF is missing expected text: {value}"
        for value in expected_text
        if not _contains_pdf_text(normalized_text, value)
    )


def extract_pdf_text(pdf_path: Path, *, timeout: float = 30.0) -> str:
    """Extract machine-readable text with the local pdftotext utility."""
    command = shutil.which("pdftotext")
    if command is None:
        raise RenderingError("pdftotext is not installed. Install the PDF text extraction tool and rerun validation.")
    try:
        result = subprocess.run(
            [command, str(pdf_path), "-"], capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as error:
        raise RenderingError(f"PDF text extraction timed out after {timeout:g} seconds.") from error
    if result.returncode != 0:
        raise RenderingError("PDF text extraction failed.")
    return result.stdout


def _normalize_pdf_text(value: str) -> str:
    """Make PDF extraction whitespace and Unicode differences non-semantic."""
    normalized = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", " ", normalized).strip()


def _contains_pdf_text(text: str, expected: str) -> bool:
    normalized_expected = _normalize_pdf_text(expected)
    if normalized_expected in text:
        return True
    return re.sub(r"\s+", "", normalized_expected) in re.sub(r"\s+", "", text)


def _render_experience(resume: ResumeDocument) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "company": _latex(company.company),
            "location": _latex(company.location or ""),
            "roles": tuple(
                {
                    "position": _latex(role.position),
                    "start_date": _latex(role.start_date),
                    "end_date": _latex(role.end_date or "Present"),
                    "bullets": tuple({"text": _latex(bullet.text)} for bullet in role.bullets),
                    "tech_stack": tuple(_latex(skill) for skill in role.tech_stack),
                }
                for role in company.roles
            ),
        }
        for company in resume.experience
    )


def _render_earlier_experience(resume: ResumeDocument) -> dict[str, object] | None:
    if resume.earlier_experience is None:
        return None
    block = resume.earlier_experience
    return {
        "position": _latex(block.position),
        "start_date": _latex(block.start_date),
        "end_date": _latex(block.end_date),
        "bullets": tuple({"text": _latex(bullet.text)} for bullet in block.bullets),
        "tech_stack": tuple(_latex(skill) for skill in block.tech_stack),
    }


def _render_education(resume: ResumeDocument) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "institution": _latex(item.institution),
            "degree_line": _latex(item.degree_line),
            "start_date": _latex(item.start_date or ""),
            "end_date": _latex(item.end_date or ""),
            "details": tuple(_latex(detail) for detail in item.details),
        }
        for item in resume.education
    )


def _render_skill_groups(resume: ResumeDocument) -> tuple[dict[str, str], ...]:
    groups: dict[str, list[str]] = {}
    for skill in resume.skills.skills:
        groups.setdefault(skill.group, []).append(_latex(skill.name))
    return tuple(
        {"category": _latex(category), "keywords": ", ".join(values)} for category, values in groups.items() if values
    )


def _font_value(name: str, default: str) -> str:
    return os.getenv(name, default).strip() or default


def _latex(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in value)


def _latex_url(value: str) -> str:
    return _latex(value).replace(r"\textbackslash{}", "/")


def _last_output(stdout: str, stderr: str) -> str:
    output = (stderr or stdout).strip().splitlines()
    return output[-1] if output else "no compiler diagnostics"
