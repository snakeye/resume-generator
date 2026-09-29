import json
import re
import shutil
from pathlib import Path
from types import SimpleNamespace

from resume_generator.generation import ResumePipeline, _report, _run_pdf_validation
from resume_generator.issue import ResumeTask
from resume_generator.profile import load_profile
from resume_generator.provider import LLMResponse, LLMUsage
from resume_generator.rendering import validate_pdf


class SequenceProvider:
    provider_name = "synthetic"
    model = "synthetic-model"

    def __init__(self, payloads):
        self.payloads = iter(payloads)

    def generate_json(self, _request):
        return LLMResponse(payload=next(self.payloads), provider=self.provider_name, model=self.model, usage=LLMUsage())


def copy_example_profile(root: Path) -> None:
    source = Path("data/examples/profile")
    destination = root / "data/profile"
    destination.mkdir(parents=True)
    for name in ("profile", "preferences", "voice", "aliases"):
        shutil.copyfile(source / f"{name}.example.yaml", destination / f"{name}.yaml")


def test_pipeline_writes_publishable_artifacts_from_synthetic_stages(tmp_path):
    copy_example_profile(tmp_path)
    provider = SequenceProvider(
        [
            {
                "schema_version": 1,
                "role": "Senior Software Engineer",
                "requirements": [
                    {"id": "req-01", "text": "Python experience", "priority": "must_have"},
                    {"id": "req-02", "text": "Kubernetes experience", "priority": "must_have"},
                ],
                "responsibilities": [],
                "technologies": ["Python"],
                "domains": [],
                "signals": [],
            },
            {
                "schema_version": 2,
                "matches": [
                    {"requirement_id": "req-01", "source_paths": ["work[0].facts[0]"], "strength": "strong"},
                ],
            },
            {"schema_version": 2, "matches": []},
            {"schema_version": 2, "matches": []},
            {
                "schema_version": 3,
                "selected": [
                    {"fact_path": "work[0].facts[0]", "covers": ["req-01"]},
                    {"fact_path": "work[0].facts[1]", "covers": []},
                    {"fact_path": "work[1].facts[0]", "covers": []},
                ],
            },
            {"schema_version": 1, "text": "Senior Backend Engineer", "fact_paths": ["work[0].facts[0]"]},
            {
                "schema_version": 2,
                "bullets": [
                    {"text": "Reduced API response time by 35%.", "fact_paths": ["work[0].facts[0]"]},
                    {"text": "Led technical planning for five engineers.", "fact_paths": ["work[0].facts[1]"]},
                    {"text": "Built event-driven services.", "fact_paths": ["work[1].facts[0]"]},
                ],
            },
            {"schema_version": 1, "text": "Improves reliable backend systems.", "fact_paths": ["work[0].facts[0]"]},
            {
                "schema_version": 1,
                "summary": {"text": "Improves reliable backend systems.", "fact_paths": ["work[0].facts[0]"]},
                "bullets": [
                    {"text": "Reduced API response time by 35%.", "fact_paths": ["work[0].facts[0]"]},
                    {"text": "Led technical planning for five engineers.", "fact_paths": ["work[0].facts[1]"]},
                    {"text": "Built event-driven services.", "fact_paths": ["work[1].facts[0]"]},
                ],
            },
        ]
    )

    def fake_compiler(tex_path, output_dir):
        pdf_path = output_dir / "compiled.pdf"
        pdf_path.write_bytes(b"synthetic pdf")
        return pdf_path

    pipeline = ResumePipeline(
        root=tmp_path,
        provider=provider,
        compiler=fake_compiler,
        pdf_validator=validate_pdf,
        pdf_extractor=lambda _path: " ".join(
            (
                "Alex Example",
                "Senior Backend Engineer",
                "Improves reliable backend systems.",
                "Summary",
                "Skills & Core Competencies",
                "Architecture & Backend",
                "Python",
                "PostgreSQL",
                "System Design",
                "Technical Leadership",
                "Kafka",
                "AWS",
                "Alex Example",
                "alex@example.com",
                "+49 000 000000",
                "Berlin, Germany",
                "LinkedIn",
                "https://www.linkedin.com/in/alex-example",
                "Experience",
                "Example Labs GmbH",
                "Senior Software Engineer",
                "2021-04",
                "Present",
                "Reduced API response time by 35%.",
                "Led technical planning for five engineers.",
                "Python",
                "Sample Cloud AG",
                "Software Engineer",
                "2018-02",
                "2021-03",
                "Built event-driven services.",
                "Education",
                "Example Technical University",
                "Bachelor of Science in Computer Science",
                "Completed coursework and a capstone project in distributed systems.",
                "Languages",
                "English",
                "C1",
                "German",
                "B2",
            )
        ),
    )
    task = ResumeTask(
        form_version=1,
        issue_number=42,
        issue_created_at="2026-01-01T12:00:00Z",
        company="Example GmbH",
        position="Senior Software Engineer",
        language="English",
        job_description="Build reliable systems.",
    )

    result = pipeline.run(task)

    assert result.success is True
    output = tmp_path / "data/output/2026-01-01/42-example-gmbh-senior-software-engineer"
    assert sorted(path.name for path in output.iterdir()) == [
        "report.md",
        "resume.docx",
        "resume.json",
        "resume.md",
        "resume.pdf",
        "resume.tex",
        "run-metadata.json",
    ]
    report = next((tmp_path / "data/runs").glob("*/*/report.md"))
    assert report.is_file()
    assert (output / "report.md").read_text() == report.read_text()
    metadata = (output / "run-metadata.json").read_text()
    assert '"issue_number": 42' in metadata
    assert "synthetic issue body" not in metadata
    metadata_value = json.loads(metadata)
    for field in ("issue_sha256", "profile_sha256", "configuration_sha256", "prompt_sha256"):
        assert re.fullmatch(r"[0-9a-f]{64}", metadata_value[field])
    assert metadata_value["schema_versions"] == {"issue_form": 1, "profile": 1, "stage_artifact": 1}
    assert metadata_value["contract_versions"] == {"resume_request": 1}
    assert metadata_value["provider"] == {"provider_name": "synthetic", "model": "synthetic-model"}
    assert metadata_value["prompt_versions"]
    assert "Example GmbH" not in metadata
    assert "Build reliable systems." not in metadata

    report_text = report.read_text()
    assert report_text.startswith("# Profile gap report")
    assert "| Must have | 1/2 | 1/2 |" in report_text
    assert "## Profile gaps" in report_text
    assert "**req-02 (must have):** Kubernetes experience" in report_text
    assert "Next action: if this is true, add concrete evidence" in report_text
    assert "<summary>Full requirement provenance (2 requirements)</summary>" in report_text
    assert "`work[0].facts[0]` [in CV]: Reduced API response time by 35%" in report_text
    assert "### Supplemental facts selected for CV" in report_text
    assert "`work[0].facts[1]`: Led technical planning" in report_text
    assert "Requirement req-02 is not represented by selected evidence" not in report_text


def test_report_prioritizes_weak_and_unused_evidence_without_mislabeling_passthrough(tmp_path):
    copy_example_profile(tmp_path)
    profile = load_profile(tmp_path / "data/profile/profile.yaml")
    requirements = (
        SimpleNamespace(id="req-01", text="Python experience", priority="must_have"),
        SimpleNamespace(id="req-02", text="Kubernetes experience", priority="must_have"),
        SimpleNamespace(id="req-03", text="Technical leadership", priority="important"),
        SimpleNamespace(id="req-04", text="Event-driven systems", priority="important"),
        SimpleNamespace(id="req-05", text="PostgreSQL experience", priority="nice_to_have"),
        SimpleNamespace(id="req-06", text="English fluency", priority="nice_to_have"),
        SimpleNamespace(id="req-07", text="Computer science degree", priority="nice_to_have"),
        SimpleNamespace(id="req-08", text="Remote-first team", priority="context"),
    )
    matches = (
        SimpleNamespace(requirement_id="req-01", source_paths=("work[0].facts[0]",), strength="strong"),
        SimpleNamespace(requirement_id="req-03", source_paths=("work[0].facts[1]",), strength="partial"),
        SimpleNamespace(requirement_id="req-04", source_paths=("work[1].facts[0]",), strength="strong"),
        SimpleNamespace(requirement_id="req-05", source_paths=("work[0].skills[1]",), strength="strong"),
        SimpleNamespace(requirement_id="req-06", source_paths=("languages[0]",), strength="strong"),
        SimpleNamespace(requirement_id="req-07", source_paths=("education[0]",), strength="strong"),
    )
    fact = SimpleNamespace(text="text", fact_paths=("work[0].facts[0]",))
    state = {
        "vacancy": SimpleNamespace(requirements=requirements),
        "matchings": (SimpleNamespace(matches=matches),),
        "selection": SimpleNamespace(selected=(SimpleNamespace(fact_path="work[0].facts[0]", covers=("req-01",)),)),
        "profile": profile,
        "resume": SimpleNamespace(
            headline=fact,
            summary=SimpleNamespace(fact_paths=()),
            experience=(SimpleNamespace(roles=(SimpleNamespace(bullets=(fact,)),)),),
            earlier_experience=None,
        ),
        "validation": SimpleNamespace(
            issues=(
                SimpleNamespace(
                    severity="warning",
                    code="text.repeated_bullet_start",
                    message="Repeated opening.",
                    path="work[0].bullets[1]",
                ),
            )
        ),
    }
    task = ResumeTask(
        form_version=1,
        company="Example GmbH",
        position="Engineer",
        language="English",
        job_description="Synthetic vacancy",
    )

    report = _report(state, task)

    assert "| Must have | 1/2 | 1/2 |" in report
    assert "| Important | 2/2 | 0/2 |" in report
    assert "| Nice to have | 3/3 | 3/3 |" in report
    assert "## Evidence to strengthen" in report
    assert "**req-03 (important):** Technical leadership" in report
    assert "## Evidence not represented in CV" in report
    assert "**req-04 (important):** Event-driven systems" in report
    assert report.count("Technical leadership") == 2
    actionable = report.split("<details>", 1)[0]
    assert "**req-05 (nice to have):** PostgreSQL experience" not in actionable
    assert "**req-06 (nice to have):** English fluency" not in actionable
    assert "**req-07 (nice to have):** Computer science degree" not in actionable
    assert "<summary>Vacancy context (1)</summary>" in report
    assert "<summary>CV quality warnings (1)</summary>" in report


def test_pdf_validation_expects_aggregated_earlier_section_not_hidden_companies():
    captured: list[str] = []

    def fake_validator(_path, expected, **_kwargs):
        captured.extend(expected)
        return ()

    resume = SimpleNamespace(
        basics=SimpleNamespace(name="Alex Example", email="", phone="", location="", links=()),
        headline=SimpleNamespace(text="Engineer"),
        summary=SimpleNamespace(text="Summary text"),
        experience=(
            SimpleNamespace(
                company="Current Company",
                roles=(
                    SimpleNamespace(position="Engineer", start_date="2020", end_date=None, bullets=(), tech_stack=()),
                ),
            ),
        ),
        skills=SimpleNamespace(skills=()),
        earlier_experience=SimpleNamespace(
            position="Earlier", start_date="2010", end_date="2019", bullets=(), tech_stack=()
        ),
        education=(),
        languages=(),
    )

    result = _run_pdf_validation(
        {"resume": resume, "pdf_path": Path("resume.pdf")},
        fake_validator,
        None,
    )

    assert result == {"valid": True, "issues": []}
    assert captured == [
        "Alex Example",
        "Engineer",
        "Summary text",
        "Summary",
        "Experience",
        "Current Company",
        "Engineer",
        "2020",
        "Present",
        "Earlier Experience",
        "Earlier",
        "2010",
        "2019",
    ]
