# Interview Prep

Help the user prepare for an interview for a tracked application.

## Inputs

- The posting (`data/job_postings/...`) and the tailored resume used.
- `profile/MASTER_CV.md` and `profile/PROFILE.md`.
- The application entry (`data/applications.json`) for stage/context.

## Process

1. Read the JD and the resume version actually sent. Align prep to what was claimed.
2. Build a prep pack:
   - Likely technical topics from the JD's stack and responsibilities.
   - Behavioral prompts mapped to the user's real accomplishments (STAR, with the
     numbers from the CV).
   - Company/role specifics worth knowing; smart questions to ask back.
3. For coding/system-design rounds, generate practice problems in the role's domain
   and review the user's solutions on correctness and fit, not just polish.
4. Save notes to `data/interview_prep/<company_role>.md` if useful across sessions.

## Honesty

Prep the user to speak truthfully to what's on their resume. Never coach claims
beyond what they actually did; the resume and the story must match.
