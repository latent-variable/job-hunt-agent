#!/usr/bin/env python3
"""
Spawn independent Claude reviewers to critique a tailored resume.

Each reviewer is a FRESH Claude instance (no shared chat context). We feed it
exactly the context that matters, the job description, the candidate's master CV,
and hard honesty rules, then ask for structured JSON feedback. Two lenses:

  text   - JD alignment, ATS keywords, wording, honesty (reads resume as text)
  visual - one-page layout, hierarchy, whitespace, contrast, theme (reads the PNG)

The point of an in-context reviewer: it sees the CV and the honesty rules, so it
will not suggest adding skills the candidate does not have (the #1 rule). Outside
feedback lacks that context and routinely suggests fabrications.

This tool runs ONE review pass and prints structured feedback. The calling agent
applies fixes, then runs it again, that loop lives in skills/review-resume.md.

Usage:
  python tools/review_resume.py --resume resumes/generated/<dir>/<file>.html \
      --jd data/job_postings/<file>.md [--cv <master_cv.md>] [--lens both] \
      [--model sonnet] [--json out.json]
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

HONESTY_RULE = (
    "CRITICAL HONESTY RULE (non-negotiable): NEVER suggest adding a skill, tool, "
    "framework, certification, employer, or experience that does not already appear "
    "in the candidate's master CV provided below. If the job wants something the CV "
    "lacks, list it under genuine_gaps and explicitly say 'do not fabricate'. Every "
    "actionable suggestion must be achievable by rewording or re-surfacing content "
    "that is already true in the CV. If unsure whether a suggestion is honest, set "
    "honesty_safe=false. Outside reviewers get this wrong; you have the CV, so you "
    "must not."
)

JSON_ONLY = (
    "Respond with ONE JSON object and nothing else. No prose, no markdown fences. "
    "Start with { and end with }."
)


def strip_html(html: str) -> str:
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    html = (html.replace("&amp;", "&").replace("&bull;", "·").replace("&rarr;", "->")
            .replace("&mdash;", "-").replace("&ndash;", "-").replace("&nbsp;", " "))
    return re.sub(r"\s+", " ", html).strip()


def extract_json(text: str) -> dict:
    """Pull the first balanced {...} object out of a model response."""
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in response")
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(text[start:i + 1])
    raise ValueError("unbalanced JSON in response")


def call_claude(prompt: str, model: str, cli: str = "claude", allow_read: bool = False,
                add_dir: Path | None = None, timeout: int = 240) -> dict:
    cmd = [cli, "-p", prompt, "--output-format", "json", "--model", model]
    if allow_read:
        cmd += ["--allowedTools", "Read"]
        if add_dir:
            cmd += ["--add-dir", str(add_dir)]
    else:
        cmd += ["--allowedTools", ""]  # text lens needs no tools
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"_error": f"reviewer timed out after {timeout}s"}
    except FileNotFoundError:
        return {"_error": f"reviewer CLI '{cli}' not found on PATH"}
    if res.returncode != 0:
        return {"_error": f"claude exited {res.returncode}: {res.stderr.strip()[:400]}"}
    try:
        envelope = json.loads(res.stdout)
        inner = envelope.get("result", res.stdout)
    except json.JSONDecodeError:
        inner = res.stdout
    try:
        return extract_json(inner)
    except ValueError as e:
        return {"_error": f"could not parse reviewer JSON: {e}", "_raw": inner[:600]}


def text_prompt(jd: str, resume_text: str, cv: str) -> str:
    return f"""You are an expert technical recruiter and resume reviewer. Review ONE tailored
resume against ONE job description. Be specific and grounded.

{HONESTY_RULE}

=== JOB DESCRIPTION ===
{jd}

=== CANDIDATE MASTER CV (ground truth for honesty) ===
{cv}

=== TAILORED RESUME (plain text) ===
{resume_text}

Score JD alignment, ATS keyword coverage, wording, and clarity. {JSON_ONLY}
Schema:
{{
  "lens": "text",
  "overall_score": <0-10 float>,
  "jd_alignment_score": <0-10 float>,
  "ats_pass_likelihood": "low|medium|high",
  "strengths": [<short strings>],
  "issues": [
    {{"severity":"high|med|low","location":"<section/line>","problem":"...","suggestion":"<reword using only true CV content>","honesty_safe":true}}
  ],
  "overclaim_flags": [<any phrasing that overstates vs the CV; [] if none>],
  "jd_keywords_in_cv_not_surfaced": [<true keywords to surface more>],
  "genuine_gaps_do_not_fabricate": [<JD wants, CV lacks>]
}}"""


def visual_prompt(png_path: Path) -> str:
    return f"""You are a design reviewer for one-page resumes. Use the Read tool to open the
image at this exact path, then critique its visual presentation:

  {png_path}

Judge: one-page fit and balance, visual hierarchy, whitespace/density, alignment,
color contrast and readability, theme distinctiveness and professionalism, and any
clipping or overflow. Do NOT comment on wording or job fit (another reviewer does that).
{JSON_ONLY}
Schema:
{{
  "lens": "visual",
  "overall_score": <0-10 float>,
  "one_page_balanced": true,
  "strengths": [<short strings>],
  "issues": [
    {{"severity":"high|med|low","area":"hierarchy|whitespace|alignment|contrast|readability|theme|clipping","problem":"...","suggestion":"..."}}
  ]
}}"""


STYLE_RULE = (
    "WRITING STYLE (flag violations): no em or en dashes as separators (use commas, "
    "semicolons, or restructure); no 'X, not Y' constructions; no cliche closers ('I "
    "look forward to discussing'); no meta-commentary on the company's strategy; no "
    "philosophical openers about the product; no perfectly balanced triads; active "
    "voice; short, direct sentences that react to JD specifics. These read as AI-written "
    "and recruiters flag them instantly."
)


def cover_text_prompt(jd: str, letter_text: str, cv: str, resume_text: str | None) -> str:
    resume_block = f"\n=== THE TAILORED RESUME (letter must complement, not repeat) ===\n{resume_text}\n" if resume_text else ""
    return f"""You are an expert recruiter reviewing ONE cover letter for ONE job. Judge whether it
reacts to THIS posting specifically, proves fit with real evidence, complements (does
not just repeat) the resume, stays honest, and avoids AI-tell writing.

{HONESTY_RULE}

{STYLE_RULE}
{resume_block}
=== JOB DESCRIPTION ===
{jd}

=== CANDIDATE MASTER CV (ground truth for honesty) ===
{cv}

=== COVER LETTER (plain text) ===
{letter_text}

Check the arc (specific hook -> production proof with numbers -> role alignment ->
differentiator -> direct close), JD reaction, honesty vs CV, and writing style. {JSON_ONLY}
Schema:
{{
  "lens": "cover-letter-text",
  "overall_score": <0-10 float>,
  "jd_reaction_score": <0-10 float, how specifically it reacts to THIS posting>,
  "arc_present": {{"hook":true,"proof_with_numbers":true,"role_alignment":true,"differentiator":true,"direct_close":true}},
  "complements_resume": true,
  "strengths": [<short strings>],
  "issues": [
    {{"severity":"high|med|low","location":"<paragraph/line>","problem":"...","suggestion":"<reword using only true content>","honesty_safe":true}}
  ],
  "overclaim_flags": [<phrasing that overstates vs CV; [] if none>],
  "llm_isms_or_cliches": [<em-dashes, 'I look forward to', meta-strategy talk, balanced triads, etc.; [] if none>]
}}"""


def cover_visual_prompt(png_path: Path, companion_png: Path | None) -> str:
    companion = ""
    if companion_png:
        companion = (f"\nAlso Read the matching RESUME image at this path and judge whether the two read "
                     f"as one cohesive application package (same theme, fonts, color, header):\n  {companion_png}\n")
    return f"""You are a design reviewer for a one-page cover letter. Use the Read tool to open the
image at this exact path, then critique its visual presentation:

  {png_path}
{companion}
Judge: one-page fit, readability and line length, professional letter layout (header,
date, greeting, body, signature), whitespace, and theme consistency with the resume if
provided. Do NOT comment on wording or job fit (another reviewer does that). {JSON_ONLY}
Schema:
{{
  "lens": "cover-letter-visual",
  "overall_score": <0-10 float>,
  "one_page": true,
  "matches_resume_theme": "yes|no|not_provided",
  "strengths": [<short strings>],
  "issues": [
    {{"severity":"high|med|low","area":"layout|whitespace|readability|theme|alignment|clipping","problem":"...","suggestion":"..."}}
  ]
}}"""


def resolve_cv(arg: str | None) -> Path | None:
    if arg:
        return Path(arg)
    for cand in [PROJECT_ROOT / "profile" / "MASTER_CV.md"]:
        if cand.exists():
            return cand
    hits = sorted(PROJECT_ROOT.glob("*[Cc][Vv]*.md")) or sorted(PROJECT_ROOT.glob("*_CV_*.md"))
    return hits[0] if hits else None


def print_report(label: str, data: dict) -> None:
    print(f"\n{'='*70}\n  {label}\n{'='*70}")
    if "_error" in data:
        print(f"  ERROR: {data['_error']}")
        if "_raw" in data:
            print(f"  raw: {data['_raw']}")
        return
    print(json.dumps(data, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser(description="Spawn independent Claude reviewers for a resume or cover letter")
    ap.add_argument("--resume", required=True, help="path to the document .html (resume or cover letter)")
    ap.add_argument("--jd", required=True, help="path to the job description (.md/.txt)")
    ap.add_argument("--cv", help="master CV path (auto-detected if omitted)")
    ap.add_argument("--type", choices=["resume", "cover-letter"], default="resume",
                    help="document type (default: resume)")
    ap.add_argument("--companion", help="cover-letter only: the matching resume .html/.png to "
                    "check theme consistency and that the letter complements (not repeats) it")
    ap.add_argument("--lens", choices=["text", "visual", "both"], default="both")
    ap.add_argument("--model", default="sonnet", help="reviewer model (default: sonnet)")
    ap.add_argument("--cli", default="claude",
                    help="reviewer CLI in headless mode (default: claude). Must accept "
                         "'-p PROMPT --output-format json'.")
    ap.add_argument("--json", help="write combined feedback to this JSON file")
    args = ap.parse_args()

    # Reviewer CLI may not exist in every harness (Codex, Gemini/agy, Pi, Cursor...).
    # Fail loud and clear so the caller never silently skips the review gate.
    if shutil.which(args.cli) is None:
        print(
            "\n" + "=" * 70 +
            "\n  REVIEW CYCLE UNAVAILABLE\n" + "=" * 70 +
            f"\n  The reviewer CLI '{args.cli}' was not found on PATH, so the automated"
            "\n  review could not run."
            "\n"
            "\n  DO NOT mark this document complete. Tell the user the review cycle was"
            "\n  skipped, then choose one:"
            "\n    1. Install the Claude CLI (claude.ai/code) and re-run this command."
            "\n    2. Point --cli at another agent CLI that supports headless"
            "\n       '-p PROMPT --output-format json' (e.g. --cli <your-cli>)."
            "\n    3. Run the review by hand with whatever agent you have: feed it the"
            "\n       job description, the master CV, and the honesty rubric, and ask"
            "\n       for the same critique (see skills/review-resume.md or review-cover-letter.md)."
            "\n"
            "\n  Until reviewed, leave the application status at 'tailoring'.\n",
            file=sys.stderr,
        )
        return 3

    resume = Path(args.resume)
    if not resume.exists():
        print(f"Resume not found: {resume}", file=sys.stderr)
        return 1
    png = resume.with_suffix(".png")
    jd_path = Path(args.jd)
    cv_path = resolve_cv(args.cv)
    if not jd_path.exists():
        print(f"JD not found: {jd_path}", file=sys.stderr)
        return 1
    if not cv_path or not cv_path.exists():
        print("Master CV not found; pass --cv. Honesty grounding requires it.", file=sys.stderr)
        return 1

    jd = jd_path.read_text()
    cv = cv_path.read_text()
    out: dict = {"resume": str(resume), "jd": str(jd_path), "cv": str(cv_path)}

    # Companion resume (for cover-letter theme + non-duplication checks)
    companion_png = None
    companion_text = None
    if args.companion:
        comp = Path(args.companion)
        cpng = comp.with_suffix(".png")
        companion_png = cpng if cpng.exists() else None
        if comp.suffix.lower() in (".html", ".htm") and comp.exists():
            companion_text = strip_html(comp.read_text())

    if args.lens in ("text", "both"):
        doc_text = strip_html(resume.read_text())
        print(f"Spawning text reviewer (independent {args.cli})...", file=sys.stderr)
        prompt = (cover_text_prompt(jd, doc_text, cv, companion_text)
                  if args.type == "cover-letter" else text_prompt(jd, doc_text, cv))
        out["text"] = call_claude(prompt, args.model, cli=args.cli)
        print_report("TEXT / JD-MATCH REVIEW", out["text"])

    if args.lens in ("visual", "both"):
        if not png.exists():
            out["visual"] = {"_error": f"PNG not found: {png}. Render the document first."}
        else:
            print(f"Spawning visual reviewer (independent {args.cli}, reads the PNG)...", file=sys.stderr)
            vprompt = (cover_visual_prompt(png.resolve(), companion_png.resolve() if companion_png else None)
                       if args.type == "cover-letter" else visual_prompt(png.resolve()))
            out["visual"] = call_claude(vprompt, args.model, cli=args.cli, allow_read=True,
                                        add_dir=resume.parent.resolve())
        print_report("VISUAL PRESENTATION REVIEW", out["visual"])

    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=2))
        print(f"\nWrote {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
