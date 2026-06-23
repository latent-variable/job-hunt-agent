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


def call_claude(prompt: str, model: str, allow_read: bool = False,
                add_dir: Path | None = None, timeout: int = 240) -> dict:
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--model", model]
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
    ap = argparse.ArgumentParser(description="Spawn independent Claude resume reviewers")
    ap.add_argument("--resume", required=True, help="path to the tailored resume .html")
    ap.add_argument("--jd", required=True, help="path to the job description (.md/.txt)")
    ap.add_argument("--cv", help="master CV path (auto-detected if omitted)")
    ap.add_argument("--lens", choices=["text", "visual", "both"], default="both")
    ap.add_argument("--model", default="sonnet", help="reviewer model (default: sonnet)")
    ap.add_argument("--json", help="write combined feedback to this JSON file")
    args = ap.parse_args()

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

    if args.lens in ("text", "both"):
        resume_text = strip_html(resume.read_text())
        print("Spawning text/JD reviewer (independent Claude)...", file=sys.stderr)
        out["text"] = call_claude(text_prompt(jd, resume_text, cv), args.model)
        print_report("TEXT / JD-MATCH REVIEW", out["text"])

    if args.lens in ("visual", "both"):
        if not png.exists():
            out["visual"] = {"_error": f"PNG not found: {png}. Render the resume first."}
        else:
            print("Spawning visual reviewer (independent Claude, reads the PNG)...", file=sys.stderr)
            out["visual"] = call_claude(visual_prompt(png.resolve()), args.model,
                                        allow_read=True, add_dir=resume.parent.resolve())
        print_report("VISUAL PRESENTATION REVIEW", out["visual"])

    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=2))
        print(f"\nWrote {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
