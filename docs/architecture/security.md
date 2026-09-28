# Security Model

## Trust Boundaries

These values are untrusted input:

- issue title and body;
- company and position;
- job description;
- additional preferences;
- issue comments;
- provider responses.

They are data, not instructions to the runner. They cannot change security,
privacy, factuality, validation, filesystem, Git, or GitHub rules.

## Credentials

GitHub authentication comes from GitHub CLI. The DeepSeek API key comes from
an ignored `.env`. Secrets must never enter prompts, logs, comments, generated
artifacts, or exception messages sent to GitHub.

## Runner Authority

Only deterministic runner code may:

- change labels;
- post comments;
- create commits and branches;
- push;
- create Pull Requests.

LLM stages return structured data. They do not have credentials, tools,
filesystem access, or GitHub access.

## Git Safety

Before claiming work, the runner verifies the repository, remote, base branch,
and clean working tree. It never resets or cleans unexpected user work.

Publishing stages only expected files under the current
`data/output/<issue-date>/<issue-number>-<company>-<position>/` directory and
inspects the staged diff before commit.

## Prompt Injection

Every LLM system prompt states that supplied content is untrusted data and
instructions inside it must not be followed. Regression tests cover requests
to expose secrets, read files, alter GitHub, or fabricate experience.

Prompt wording is defense in depth. The real boundary is that the model never
receives credentials or tools capable of those actions.
