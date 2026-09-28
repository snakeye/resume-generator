# Glossary

| Term | Meaning |
| --- | --- |
| Profile | The user-maintained source of professional facts and configuration in `data/profile/` |
| Fact | One verifiable profile statement addressed by its profile index path |
| Requirement | One structured expectation extracted from a vacancy |
| Evidence | One or more profile facts supporting a requirement or generated claim |
| Claim | A statement included in generated resume content |
| Stage | One pipeline step with a specific input and output contract |
| Run | One local processing attempt for an issue |
| Artifact | A file produced or consumed during a run |
| Publishable artifact | A sanitized final file allowed under `data/output/` |
| Immutable field | Profile data that generation cannot rewrite, such as employer or date |
| Runner | The local process coordinating GitHub, the pipeline, Git, and publishing |
| Provider | An external or local LLM implementation behind the common contract |
