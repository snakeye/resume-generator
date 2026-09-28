# Security Policy

Do not report vulnerabilities through public Issues when a report could
contain credentials, profile data, prompts, generated resumes, or runner logs.
Use GitHub's private vulnerability reporting when it is enabled for the
repository.

Never include these values in a report:

- `.env` contents;
- GitHub or LLM tokens;
- real `data/profile/` files;
- raw LLM request payloads;
- unredacted `data/runs/` or `data/logs/` files.

The security and privacy model is documented in
[`docs/architecture/security.md`](docs/architecture/security.md) and
[`docs/privacy.md`](docs/privacy.md).
