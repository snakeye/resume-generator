# Published Output

The runner writes reviewable artifacts to
`data/output/<issue-date>/<issue-number>-<company>-<position>/` and commits only
that issue directory to its resume branch.

Expected files:

```text
resume.json
resume.md
resume.tex
resume.pdf
resume.docx
report.md
run-metadata.json
```

Raw prompts, LLM responses, profile data, cache entries, and logs must never
be copied here.
