# Track Company

Add or update a company in `data/companies.json`.

## When to use

- The user names a company they want watched.
- A job search surfaces a company worth scanning regularly.

## Fields

```json
{
  "name": "Company",
  "slug": "ats-slug",
  "platform": "greenhouse | lever | ashby | eightfold | talentbrew | custom",
  "careers_url": "https://...",
  "notes": "what they do, why it fits, comp if known",
  "pay_range": null,
  "roles_of_interest": ["Senior SWE", "ML Engineer"],
  "last_checked": "YYYY-MM-DD"
}
```

## Process

1. Find the ATS platform + slug. Verify with a quick API fetch before saving:
   - Greenhouse: `boards-api.greenhouse.io/v1/boards/{slug}/jobs`
   - Lever: `api.lever.co/v0/postings/{slug}`
   - Ashby: `api.ashbyhq.com/posting-api/job-board/{slug}`
2. If the ATS is unsupported, set `platform: "custom"` and note it needs a manual check.
3. Add via CLI or edit the JSON directly:
   ```bash
   python tools/pipeline.py add "Company" slug greenhouse --careers-url https://...
   ```
4. Set `last_checked` to today.
