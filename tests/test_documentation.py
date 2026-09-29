import re
from pathlib import Path


def test_local_markdown_links_resolve():
    missing = []
    documents = list(Path.cwd().glob("*.md"))

    for directory in (".agents", ".github", "data", "docs", "tests"):
        documents.extend(Path(directory).rglob("*.md"))

    for document in documents:
        for link in re.findall(r"\[[^]]+]\(([^)]+)\)", document.read_text()):
            target = link.split("#", 1)[0]
            if not target or "://" in target:
                continue
            if not (document.parent / target).resolve().exists():
                missing.append(f"{document}: {link}")

    assert not missing, "Missing local links:\n" + "\n".join(missing)


def test_issue_form_and_scope_match_mvp_contract():
    issue_form = (Path(".github/ISSUE_TEMPLATE/generate-resume.yml")).read_text()
    scope = Path("docs/product/scope.md").read_text()

    assert "- English" in issue_form
    assert "- German" not in issue_form
    assert "English resume requests only" in scope
    assert "JSON, Markdown, TeX, PDF, DOCX, report, and metadata output" in scope
