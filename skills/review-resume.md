# Review Resume (automated, independent reviewers)

Critique a tailored resume with **fresh Claude instances** that have no shared chat
context, only the context that matters: the job description, the master CV, and the
honesty rules. Then loop: review → apply fixes → review again, until clean.

Why independent reviewers beat inline self-review or outside feedback:
- **Fresh eyes.** A reviewer that didn't write the resume catches what the author rationalizes.
- **In-context honesty.** It sees the CV, so it cannot suggest adding skills the
  candidate lacks (the #1 rule). Outside reviewers routinely suggest fabrications.
- **Two lenses, separated.** Text/JD-match and visual presentation are different
  jobs; splitting them keeps each critique focused.

## Tool

`tools/review_resume.py` spawns the reviewers via the `claude` CLI (`-p` headless,
`--output-format json`). Each call is a separate process with its own context.

```bash
python tools/review_resume.py \
  --resume resumes/generated/<company_role>/<file>.html \
  --jd data/job_postings/<company_role>.md \
  --cv <master_cv.md> \
  --lens both --model sonnet \
  --json data/scan_results/<company_role>_review.json
```

- `--lens text` , JD alignment, ATS keywords, wording, honesty (reads resume as text).
- `--lens visual` , one-page layout, hierarchy, whitespace, contrast, theme (reads the PNG; render first).
- `--cv` is required grounding for honesty. Auto-detects `profile/MASTER_CV.md` or a `*CV*.md`.
- `--model` defaults to `sonnet` (independent from the author model; cheaper, fast).

## The loop (you drive this)

1. **Tailor + render** the resume so the `.html` and `.png` both exist and it passes the one-page check.
2. **Review:** run the tool, `--lens both`.
3. **Triage the feedback against the honesty bar FIRST:**
   - Apply every `overclaim_flags` / honesty fix immediately, these are non-negotiable.
   - Apply `honesty_safe: true` suggestions that improve JD alignment or visuals.
   - For `genuine_gaps_do_not_fabricate`, do NOT add the skill. Leave the gap.
   - Ignore suggestions that would break the one-page rule unless you can trade space.
4. **Re-render**, confirm one page.
5. **Review again** (a new independent instance). Repeat until: no high-severity
   issues, no overclaim flags, and scores plateau.
6. Note in the application entry which round it passed.

## Hard rules for the loop

- **Never add a skill, tool, or title the CV does not support**, even if a reviewer
  asks for it. The reviewer is grounded in the CV and should not, but if it slips,
  you are the backstop. A flagged JD keyword the candidate lacks stays a gap.
- **One page always wins.** A suggestion that overflows the page gets traded against
  an existing weaker line, not appended.
- Stop when it's clean. Don't chase a 10/10, diminishing returns past "no high
  issues, no overclaims, reads well."

## Requirements

- `claude` CLI installed and authenticated (`claude --version`), or another headless
  agent CLI passed via `--cli` that accepts `-p PROMPT --output-format json`.
- The resume rendered to PNG (`render-resume.sh`) before a visual review.

## If the reviewer CLI is missing (other harnesses)

This tool drives the `claude` CLI by default. Agents run in many harnesses (Codex,
Gemini/agy, Pi, Cursor) that may not have it. If the CLI is absent, the tool exits
**code 3** with a "REVIEW CYCLE UNAVAILABLE" notice and runs nothing. When that
happens:

1. **Do not silently finish or claim the resume passed review.**
2. **Tell the user plainly** the automated review cycle could not run.
3. Recommend one of: install the Claude CLI; pass `--cli <your-cli>` if your agent
   has a compatible headless `-p ... --output-format json` mode; or run the review
   manually, hand your own agent the JD, the master CV, and the honesty rubric above
   (JD-match + visual lenses, never suggest skills not in the CV) and apply the loop
   by hand.
4. Leave the application at `tailoring`, flagged unreviewed, until a review is done.
