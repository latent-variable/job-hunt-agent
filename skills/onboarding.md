# Onboarding

Run this the first time someone uses the repo, or whenever `profile/PROFILE.md`
and `profile/MASTER_CV.md` still contain `<!-- ... -->` placeholders. Goal: turn
a generic clone into *this user's* personal job agent.

Do not recommend jobs, tailor resumes, or invent a profile until this is done (or
the user explicitly says to skip a step).

## Conversation flow

Be brief and ask in small batches, not a 20-question wall. Confirm as you go.

### 1. Find their CV / resume
Ask: "Where's your current resume or CV? Give me a file path, paste the text, or
point me at a LinkedIn / portfolio URL." Read whatever they give you.
- If they have nothing written, interview them: roles held, companies, dates,
  biggest wins (with numbers), education.

### 2. Walk their projects / repos
Ask: "Which projects or repos do you want highlighted? Point me at local folders
or GitHub and I'll read them for accurate detail." For each:
- Read the source / README / git history (use `gh` for GitHub).
- Pull out what it does, the stack, scale/impact, and a one-line framing.
- This is what makes bullets specific instead of generic. Spend real effort here.

### 3. Capture preferences
Ask for (batch these):
- Target roles and seniority.
- Location rules: on-site metro? hybrid? US-remote? relocation OK? hard nos?
- Industry priorities and any deal-breakers.
- Salary: track-only or a hard floor?

### 4. Capture their rules
Ask:
- Honest years of experience (never to be padded).
- Anything they did NOT own and don't want claimed.
- Style preferences (default: one-page, active voice, no LLM-isms) — keep or change?

## Write it down

Populate, removing all placeholder comments:

1. **`profile/PROFILE.md`** — identity, preferences, positioning, projects table,
   honesty rules, style rules.
2. **`profile/MASTER_CV.md`** — full master CV built from their resume + the
   project walk. Reverse-chronological, quantified, complete. This is the source
   every tailored resume is cut from.
3. **`profile/ranking_profile.json`** — copy from `ranking_profile.example.json`
   and fill `skills`, `experience_keywords`, `target_seniority`,
   `years_experience`, `direct_role_signals`, `builder_role_signals` from their
   CV so `tools/rank_jobs.py` scores jobs for *them*.
4. **`data/companies.json`** — seed with any companies they already care about
   (`tools/pipeline.py add "Name" slug platform --careers-url ...`), or run
   `python3 tools/pipeline.py seed` if you add starter companies.

## Verify and hand off

- Confirm the base template header (`resumes/templates/base.html`) reflects their
  name/contact, or note you'll fill it per-resume.
- Run a smoke test: `cd html2pdf && npm install` once, then confirm
  `./render-resume.sh` works on a sample.
- Summarize what you captured and ask: "Want to start a job search now, or refine
  the profile first?"

After onboarding, normal operation: search → track → tailor → update CV → render.
