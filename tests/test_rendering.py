from pathlib import Path

from docx import Document

from resume_generator.assembly import assemble_resume
from resume_generator.headline import Headline
from resume_generator.profile import EarlierExperiencePreferences, load_profile
from resume_generator.rendering import (
    expected_rendered_text,
    render_docx,
    render_latex,
    render_markdown,
    render_resume,
    validate_docx,
    validate_pdf,
)
from resume_generator.skills import SkillsSelection
from resume_generator.voice import VoiceAdaptation

PROFILE = load_profile(Path("data/examples/profile/profile.example.yaml"))


def make_resume():
    return assemble_resume(
        PROFILE,
        Headline.model_validate(
            {"schema_version": 1, "text": "Backend & Platform", "fact_paths": ["work[0].facts[0]"]}
        ),
        VoiceAdaptation.model_validate(
            {
                "schema_version": 1,
                "summary": {"text": "Builds reliable systems.", "fact_paths": ["work[0].facts[0]"]},
                "bullets": [{"text": "Reduced API latency by 35%.", "fact_paths": ["work[0].facts[0]"]}],
            }
        ),
        SkillsSelection.model_validate(
            {
                "schema_version": 2,
                "skills": (
                    {
                        "category": "technology",
                        "group": "Architecture & Backend",
                        "name": "Python",
                        "canonical": "python",
                    },
                ),
            }
        ),
    )


def test_latex_escapes_user_controlled_characters():
    latex = render_latex(make_resume())

    assert r"Backend \& Platform" in latex
    assert r"35\%" in latex
    assert (
        r"LinkedIn: \href{https://www.linkedin.com/in/alex-example}{https://www.linkedin.com/in/alex-example}" in latex
    )


def test_latex_omits_empty_bullet_lists():
    latex = render_latex(make_resume())

    assert latex.count(r"\begin{itemize}") == 4
    assert latex.count(r"\end{itemize}") == 4
    assert "Completed coursework and a capstone project in distributed systems." in latex


def test_latex_uses_cvbot_layout_and_profile_sections():
    latex = render_latex(make_resume())

    assert r"\usepackage{fontspec}" in latex
    assert r"\geometry{margin=0.85in}" in latex
    assert r"\Needspace{10\baselineskip}" in latex
    assert r"\section*{Education}" in latex
    assert r"\section*{Languages}" in latex


def test_latex_renders_multiple_profile_skill_groups():
    resume = make_resume().model_copy(
        update={
            "skills": SkillsSelection.model_validate(
                {
                    "schema_version": 2,
                    "skills": (
                        {
                            "category": "technology",
                            "group": "Architecture & Backend",
                            "name": "Python",
                            "canonical": "python",
                        },
                        {
                            "category": "competency",
                            "group": "Leadership & Delivery",
                            "name": "Technical Leadership",
                            "canonical": "technical leadership",
                        },
                    ),
                }
            )
        }
    )

    latex = render_latex(resume)

    assert r"Architecture \& Backend" in latex
    assert r"Leadership \& Delivery" in latex


def test_latex_renders_earlier_experience_block():
    profile = PROFILE.model_copy(
        update={
            "preferences": PROFILE.preferences.model_copy(
                update={"earlier_experience": EarlierExperiencePreferences(detailed_positions=1)}
            )
        }
    )
    resume = assemble_resume(
        profile,
        Headline.model_validate({"schema_version": 1, "text": "Backend", "fact_paths": ["work[0].facts[0]"]}),
        VoiceAdaptation.model_validate(
            {
                "schema_version": 1,
                "summary": {"text": "Engineer.", "fact_paths": ["work[0].facts[0]"]},
                "bullets": [
                    {"text": "Built older systems.", "fact_paths": ["work[1].facts[0]"]},
                ],
            }
        ),
        SkillsSelection.model_validate({"schema_version": 2, "skills": ()}),
    )

    latex = render_latex(resume)

    assert r"\section*{Earlier Experience}" in latex
    assert "Software Engineer / Team Lead" in latex
    assert "Sample Cloud AG" not in latex


def test_render_resume_writes_tex_and_uses_compiler(tmp_path):
    def fake_compiler(tex_path, output_dir):
        pdf_path = output_dir / "compiled.pdf"
        pdf_path.write_bytes(b"synthetic pdf")
        return pdf_path

    tex_path, pdf_path = render_resume(make_resume(), tmp_path, compiler=fake_compiler)

    assert tex_path.name == "resume.tex"
    assert pdf_path.name == "resume.pdf"
    assert pdf_path.read_bytes() == b"synthetic pdf"


def test_render_markdown_contains_resume_sections_and_escapes_markup(tmp_path):
    path = render_markdown(make_resume(), tmp_path)
    markdown = path.read_text(encoding="utf-8")

    assert "# Alex Example" in markdown
    assert "## Experience" in markdown
    assert "- Reduced API latency by 35%." in markdown
    assert "## Education" in markdown
    assert "- Completed coursework and a capstone project in distributed systems." in markdown
    assert "## Languages" in markdown


def test_render_docx_contains_resume_text_and_is_editable(tmp_path):
    path = render_docx(make_resume(), tmp_path)
    document = Document(path)
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)

    assert path.name == "resume.docx"
    assert "Alex Example" in text
    assert "Example Labs GmbH" in text
    assert "Reduced API latency by 35%." in text
    assert "Completed coursework and a capstone project in distributed systems." in text


def test_rendered_text_contract_covers_sections_and_links():
    resume = make_resume()

    pdf_expected = expected_rendered_text(resume, skills_heading="Skills & Core Competencies")
    docx_expected = expected_rendered_text(resume, skills_heading="Skills")

    assert "Skills & Core Competencies" in pdf_expected
    assert "Skills" in docx_expected
    assert "https://www.linkedin.com/in/alex-example" in pdf_expected
    assert "Senior Software Engineer" in docx_expected
    assert "2021-04" in pdf_expected
    assert "English" in docx_expected


def test_docx_validation_reports_missing_expected_content(tmp_path):
    path = render_docx(make_resume(), tmp_path)

    errors = validate_docx(path, ["Alex Example", "Missing section"])

    assert errors == ("DOCX is missing expected text: Missing section",)


def test_pdf_validation_uses_extracted_text_and_reports_missing_values(tmp_path):
    pdf_path = tmp_path / "resume.pdf"
    pdf_path.write_bytes(b"synthetic pdf")

    errors = validate_pdf(pdf_path, ["Example Labs GmbH", "Missing"], extractor=lambda path: "Example Labs GmbH")

    assert errors == ("PDF is missing expected text: Missing",)


def test_pdf_validation_ignores_extraction_whitespace_inside_value(tmp_path):
    pdf_path = tmp_path / "resume.pdf"
    pdf_path.write_bytes(b"synthetic pdf")

    errors = validate_pdf(
        pdf_path,
        ["InfluencerDB"],
        extractor=lambda path: "Influencer\nDB",
    )

    assert errors == ()
