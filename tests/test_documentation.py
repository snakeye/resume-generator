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
