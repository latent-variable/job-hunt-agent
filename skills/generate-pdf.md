# Generate PDF

Render an HTML resume (or cover letter) to a verified one-page PDF + PNG.

## First-time setup

```bash
cd html2pdf && npm install   # installs puppeteer-core (uses system Chrome)
```

If Chrome isn't at the default location, set `CHROME_PATH=/path/to/chrome`. Don't
download a bundled browser.

## Render

```bash
./render-resume.sh resumes/generated/<company_role>/<file>.html
# or:
cd html2pdf && node html-to-pdf.mjs <path-to-html>
```

Outputs `.pdf` and `.png` alongside the HTML.

## One-page check (default rule)

- `render-resume.sh` exits non-zero with overflow pixels if the PDF exceeds one
  page. Trim bullets / tighten wording until it exits 0. Don't shrink fonts below
  readability. (If the user changed the one-page rule in PROFILE.md, follow that.)
- Then **read the PNG**: clipping at edges → trim; large empty space at the bottom
  → add content back.

## Cleanup

One subfolder per application. When regenerating, remove orphaned old artifacts so
only the current version exists per folder.
