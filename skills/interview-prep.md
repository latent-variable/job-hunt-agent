# Interview Prep

Help the user prepare for an interview for a tracked application, across every stage of
the loop (recruiter screen, hiring manager, technical/coding, on-site panel).

## Inputs

- The posting (`data/job_postings/...`) and the tailored resume actually sent.
- `profile/MASTER_CV.md` and `profile/PROFILE.md`.
- The application entry (`data/applications.json`) for stage/context.
- Any recruiter emails or notes the user shares.
- The company's published hiring framework if it has one (e.g. Amazon Leadership
  Principles, Google's attributes) — load and grade against it.

## Process

1. Read the JD and the resume version actually sent. Align prep to what was claimed —
   never coach claims beyond what the user actually did. The resume and the story must match.
2. Build a prep pack for the relevant stage:
   - Likely technical topics from the JD's stack and responsibilities.
   - Behavioral prompts mapped to the user's real accomplishments (STAR, with real numbers).
   - Company/role specifics worth knowing; smart questions for the user to ask back to
     evaluate whether the role fits THEM, not only whether they fit it.
3. Run mocks one question at a time. Grade on authenticity and question-fit, not polish;
   spoken answers ramble, that's normal, don't flag it as a defect.

## Output — one folder per role (do NOT drop loose files)

When you save prep artifacts, give every role its own folder. Never scatter flat
`<company_role>.md` files into `data/interview_prep/` — they don't scale across stages
and topics.

```
data/interview_prep/<company_role>/
  _conventions.md        # cross-cutting locks — write this FIRST (see below)
  recruiter_screen.md    # one file per stage
  technical_prep.md
  onsite_panel.md
  <topic>_card.md        # talking-point banks (intro, project deep-dive, questions to ask)
  coding_challenge/      # see below
  archive/               # superseded files
```

Folder name `<company_role>` (lowercase, underscored) should match the resume folder under
`resumes/generated/`. File names are short stage/topic names; don't re-prefix the company.

### `_conventions.md` — seed it first

Before topic files, capture the locks for THIS role so they don't drift across many files:
- **Resume alignment** — the exact submitted resume path; verbal facts must match it.
- **Attribution / honesty locks** — what the user BUILT vs ADVISED on, honest year counts,
  tool framing. Non-negotiable.
- **Role logistics** — on-site/remote, comp, commute, and what to keep OUT of interviews.
- **Pipeline** — the stages and which file covers each.

## Coding-challenge tracking (guide the user through it)

For technical/coding loops, run a daily practice loop and TRACK it so progress is visible
over time:

```
data/interview_prep/<company_role>/coding_challenge/
  log.md                 # running table: date | problem | pattern | result | time | gap surfaced
  <NN>_<slug>.py         # the user's own solution per problem, kept as-is
```

Loop, one problem per session:
1. Pose ONE problem in the role's domain/difficulty. Target the user's weak areas first
   (ask them, or infer from past logs).
2. User solves in their language. If they're stuck, walk an example / pseudocode and hint —
   don't hand over the answer. Work within their structure; don't impose a textbook rewrite
   unless asked.
3. Grade on approach, correctness, and fluency (can they reason about time/space complexity
   out loud), not on polish.
4. Append a row to `log.md` (date, problem, pattern, pass/fail, time, the specific gap).
5. Save the user's solution as `<NN>_<slug>.py`. Next session, revisit a past gap before new
   material.

Surface `log.md` on request so the user sees which patterns they've mastered vs. still-shaky.

## Honesty

Prep the user to speak truthfully to what's on their resume. Never coach claims beyond what
they actually did; the resume and the spoken story must match.
