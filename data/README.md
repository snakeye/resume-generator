# Data Directory

All candidate and execution data lives under this directory.

| Path | Purpose | Git policy |
| --- | --- | --- |
| `profile/` | Real professional profile and its configurations | Ignored by default |
| `examples/` | Fully synthetic examples | Tracked |
| `runs/` | Inputs, stage outputs, raw diagnostics | Always ignored |
| `output/` | Files published in resume Pull Requests | Tracked selectively |
| `cache/` | Reusable stage cache | Always ignored |
| `logs/` | Local runner logs | Always ignored |

Application resources such as prompts, contracts, and templates belong inside
`src/resume_generator/resources/`, not here.
