# Search Jobs

Find postings matching the user's profile and preferences.

## Before searching

- Make sure onboarding is done (`profile/PROFILE.md` filled). If not, run `skills/onboarding.md`.
- Read `profile/PROFILE.md` for target roles, location rules, industry priorities.
- Read `data/applications.json` and `data/companies.json` to avoid duplicates and
  excluded (already-applied) companies.

## Process

1. Prefer repo tooling: `tools/pipeline.py`, `tools/fetch_jobs.py`,
   `tools/rank_jobs.py`, `tools/parse_job.py`.
2. Use manual web search only when the ATS is unsupported or fetchers can't pull
   current listings.
3. Honor the user's location rules from PROFILE.md (e.g. exclude non-US remote if
   they're US-only; respect "no relocation").
4. For each promising result capture: company, role, location, URL, key
   requirements, salary (if listed), and a one-line fit note.
5. Filter out anything in `applications.json` with status `applied`, `screening`,
   `interviewing`, or `offer`.
6. Present a ranked table; recommend a short top list with reasons.
7. Save selected postings to `data/job_postings/<company>_<role_short>.md` and add
   new companies to `data/companies.json`.

## Adding new companies to the scan

```bash
python tools/pipeline.py add "Company" slug greenhouse --careers-url https://...
python tools/pipeline.py scan -l "remote" -n 25
```

Verify the ATS slug works before adding (a quick fetch of the platform API). Mark
companies on unsupported ATS as `custom` so the scanner skips them.

## Output

| Company | Role | Location | Salary | URL | Fit notes |
|---------|------|----------|--------|-----|-----------|
| ... | ... | ... | ... | ... | ... |
