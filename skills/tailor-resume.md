# Tailor Resume

Generate a tailored one-page resume for a specific posting.

## Inputs

- **Job description** — from the user (pasted, URL, or a file in `data/job_postings/`).
- **Master CV** — `profile/MASTER_CV.md`.
- **User rules** — `profile/PROFILE.md` (positioning, honesty, style; these win).
- **Base template** — `resumes/templates/base.html`.

## Process

1. Read the JD: role, company, key requirements, preferred skills, tone/culture.
2. Read the master CV and PROFILE.md.
3. Select the experiences, skills, and projects that map most directly to the role.
4. Write a 2-3 sentence summary positioning the user for this specific role.
5. Rewrite bullets to mirror the JD's language and priorities; lead with what the
   role values most.
6. Apply the user's positioning and honesty rules. Never inflate years or claims.
7. Design a visual identity for the company (accent colors, fonts, header layout)
   distinct from previous resumes. Reuse the HTML structure, refresh the look.
8. Hyperlink company names and named projects to their URLs in the accent color.
9. Fill the base template; fill the header from PROFILE.md identity.
10. Save to `resumes/generated/<company_role>/<Name>_<Company>_<Role>.html`.
11. Save the JD to `data/job_postings/<company>_<role_short>.md` if not already saved.
12. Add/update `data/applications.json` (status `tailoring`).
13. Render with `./render-resume.sh`; if it exits non-zero (overflow), trim until
    it passes. Then read the PNG: clipping → trim; too much empty space → add back.
14. **Mandatory review gate — do not skip.** Run the independent review loop
    (`skills/review-resume.md`): `python tools/review_resume.py --resume <html>
    --jd <jd.md> --lens both`. Apply every honesty/overclaim fix and `honesty_safe`
    improvement, re-render, re-review until no high-severity issues and no overclaim
    flags remain. The application stays `tailoring` until it passes; only then is the
    resume done.

## Output

- Tailored HTML + verified one-page PDF + PNG in `resumes/generated/<company_role>/`.
- Passed the independent dual-lens review loop (no high-severity issues, no overclaim flags).
- `applications.json` updated.
