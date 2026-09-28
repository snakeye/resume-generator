# Professional Profile

The profile is the only source of career facts. A generated resume may select,
shorten, reorder, and rephrase those facts, but must not invent experience,
technologies, metrics, responsibilities, employers, titles, or dates.

## Files

The user-maintained profile lives in `data/profile/`:

| File | Purpose |
| --- | --- |
| `profile.yaml` | Personal details, summary, work, education, skill groups, and languages |
| `preferences.yaml` | Target roles and presentation preferences |
| `voice.yaml` | Writing style constraints |
| `aliases.yaml` | Canonical skills and equivalent terminology |

`./resume setup` creates all four files from the synthetic examples. Edit them
locally, then validate the complete profile with:

```bash
./resume profile validate
```

## `profile.yaml`

The main profile contains:

| Field | Required | Meaning |
| --- | --- | --- |
| `schema_version` | yes | Profile contract version; currently `1` |
| `basics.name` | yes | Name shown on the resume |
| `basics.email` | yes | Contact email |
| `basics.phone` | no | Contact phone |
| `basics.location` | no | Current location |
| `basics.links` | no | Labeled professional links |
| `summary` | no | General factual professional summary |
| `work` | yes | Employment history |
| `education` | no | Education history |
| `skills` | no | Legacy flat skills fallback |
| `skill_groups` | no | Explicit thematic groups for the tailored Skills section |
| `languages` | no | Human languages and honest proficiency levels |

Each work item has `company`, `position`, `start_date`, optional `end_date` and
`location`, optional `skills`, and a non-empty `facts` list. Facts are plain
strings, with no IDs or nested fields:

```yaml
work:
  - company: Example Labs GmbH
    position: Senior Software Engineer
    start_date: 2021-04
    end_date: null
    skills: [Python, PostgreSQL]
    facts:
      - Reduced API response time by 35% by redesigning database access.
      - Led technical planning for a team of five engineers.
```

The preferred global skills format is grouped and profile-backed:

```yaml
skill_groups:
  - name: Architecture & Backend
    keywords: [Python, PostgreSQL]
  - name: Platform, Data & Reliability
    keywords: [Docker, AWS]
```

Facts should express one verifiable contribution or responsibility. Use metrics
only when they are known and defensible. Do not estimate numbers to make a
resume sound stronger.

Generated claims refer to source facts by their index path, for example
`work[0].facts[1]`. Reordering work items or facts changes these paths.

## Separate Configurations

`preferences.yaml` currently supports:

```yaml
minimum_experience_bullets: 3
earlier_experience:
  detailed_positions: 4
```

`minimum_experience_bullets` defaults to `3` and controls the minimum number of
bullets generated for each work position (or for the Earlier Experience group).
When a position has fewer profile
facts, all available facts are used and no content is invented. Vacancy-matched
facts are preferred; unmatched facts selected to complete the work history do
not count as vacancy coverage.

Page limits are not configured in the profile yet; renderer page-count
validation remains a release task.

Education entries may include a `details` list for factual descriptions of
coursework, thesis work, research, or postgraduate study:

```yaml
education:
  - institution: Example Technical University
    area: Computer Science
    study_type: Bachelor of Science
    details:
      - Completed coursework and a capstone project in distributed systems.
```

`skill_groups` are emitted as separate lines only when they contain
vacancy-relevant keywords. The old flat `skills` list remains a fallback for
profiles that have not been migrated.

`earlier_experience` is optional. Set either `detailed_positions` to keep that
many newest positions detailed, or `ending_before` to group positions ending
before a `YYYY` or `YYYY-MM` boundary into one `Earlier Experience` block. The
fields are mutually exclusive; without this setting all positions remain
detailed. The grouped block is rendered as one compact entry with a shared date
range, merged stack, and bullets. Its `source_roles` retain every company,
title, and date for provenance and immutable validation.

`voice.yaml` controls presentation, never factual content:

```yaml
concise: true
first_person: false
language_background: Native synthetic-language speaker with strong English; write in clear, direct professional English
avoid: [corporate jargon, exaggerated claims]
```

`language_background` is optional style context for bullet, summary, and voice
generation. It is never mentioned in the resume, never used as career
evidence, and never permits intentional grammar mistakes or stereotypes.
It may preserve a natural non-native rhythm and slightly literal phrasing when
the profile calls for it; the result should still be clear and professional.

`aliases.yaml` maps canonical terms to equivalent names. The example contains
the skill synonym dictionary copied from `cvbot`:

```yaml
postgresql: [postgres, postgre, psql]
aws: [amazon web services]
```

## Validation And Privacy

Validation rejects unknown fields, invalid dates, invalid types, and malformed
configuration files. It never silently rewrites profile data.

All files under `data/profile/` are ignored by default. Private Git storage is
an explicit opt-in:

```bash
./resume profile enable-git --confirm
```

The command validates all profile files, verifies that the repository is
private, and updates only `.gitignore`. It does not stage, commit, or push.
