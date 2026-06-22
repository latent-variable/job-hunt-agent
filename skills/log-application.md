# Log Application

Record or update an application in `data/applications.json`.

## Entry shape

```json
{
  "company": "Company",
  "role": "Senior Software Engineer",
  "date_applied": "YYYY-MM-DD",
  "source_url": "https://...",
  "status": "applied",
  "resume_version": "resumes/generated/company_role/Name_Company_Role.pdf",
  "notes": "referral via X; comp $...; recruiter Y"
}
```

## Statuses

`researching` → `tailoring` → `applied` → `screening` → `interviewing` → `offer`
Terminal: `rejected`, `withdrawn`, `deferred`.

## Process

1. Read `data/applications.json`.
2. If the company+role exists, update its status and append a dated note. Else add a new entry.
3. Keep `resume_version` pointing at the actual rendered file used.
4. This file is the dedupe source: anything `applied`/`screening`/`interviewing`/
   `offer` must be excluded from future job recommendations.
