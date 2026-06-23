# Review Cover Letter (automated, independent reviewers)

Same idea as `skills/review-resume.md`, applied to cover letters. Spawn **fresh
Claude instances** with no shared chat context, fed the JD, the master CV, and the
companion resume, then loop: review → fix → review until clean.

Cover letters are where LLM-isms are deadliest, so this lens checks writing style
hard (no em-dashes, no "X, not Y", no cliche closers, no meta-commentary on company
strategy, no balanced triads) on top of JD reaction, arc, honesty, and theme match.

## Tool

Same tool as the resume reviewer, with `--type cover-letter`:

```bash
python tools/review_resume.py \
  --resume resumes/generated/<company_role>/<Name>_<Company>_Cover_Letter.html \
  --jd data/job_postings/<company_role>.md \
  --cv <master_cv.md> \
  --type cover-letter \
  --companion resumes/generated/<company_role>/<Name>_<Company>_<Role>.html \
  --lens both --model sonnet \
  --json data/scan_results/<company_role>_cover_review.json
```

- `--type cover-letter` swaps in the cover-letter rubrics (arc, JD reaction, style, honesty).
- `--companion <resume.html>` lets the reviewer check the letter (a) complements,
  does not just repeat, the resume, and (b) shares its visual theme (render both first).
- `--cli`, `--lens`, `--model` behave as in the resume reviewer. Missing CLI → exit
  3 with the same "REVIEW CYCLE UNAVAILABLE" notice; do not silently finish.

## What the lenses return

- **cover-letter-text:** `overall_score`, `jd_reaction_score`, `arc_present`
  (hook / proof_with_numbers / role_alignment / differentiator / direct_close),
  `complements_resume`, `issues`, `overclaim_flags`, `llm_isms_or_cliches`.
- **cover-letter-visual:** `overall_score`, `one_page`, `matches_resume_theme`,
  `issues`.

## The loop (you drive this)

1. Write the letter + render to PNG (it must pass the one-page check).
2. Review with `--type cover-letter --lens both` and the resume as `--companion`.
3. Triage, honesty first:
   - Apply every `overclaim_flags` and `llm_isms_or_cliches` fix immediately, non-negotiable.
   - Apply `honesty_safe` suggestions that sharpen JD reaction or the arc.
   - Complete the arc: every element in `arc_present` should be true, especially a
     `direct_close` (no cliche closer).
   - Genuine gaps (JD wants, CV lacks): do NOT fabricate.
4. Re-render, confirm one page, re-review until no high-severity issues, no overclaim
   flags, no LLM-isms, and the arc is complete.
5. The cover letter is not done until it passes. Same fail-safe as resumes: if the
   reviewer CLI is unavailable, tell the user and recommend an equivalent manual review.

## Requirements

- `claude` CLI (or `--cli <compatible>`), and the letter rendered to PNG first.
