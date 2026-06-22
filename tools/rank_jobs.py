#!/usr/bin/env python3
"""
Rank and score jobs against the user's CV profile.

Personalization: this script loads `profile/ranking_profile.json` if present
(written during onboarding) and falls back to generic defaults otherwise. Edit
that JSON, or the defaults below, to match your skills, target roles, and
seniority.

Scoring dimensions:
  - Skill match: profile skills found in the job posting
  - Role alignment: how directly the title and description map to target AI/builder roles
  - Experience alignment: keyword overlap between responsibilities and CV experience
  - Seniority fit: does the job level match the profile?
  - Location fit: is the job in the target area?
  - Clearance bonus: does the job value clearance?

Usage:
  python tools/rank_jobs.py <company_slug> --platform greenhouse --keywords "AI,ML" --location "la"
  python tools/rank_jobs.py searchcareers.caci.com --platform eightfold --keywords "AI,ML,architect" --location "la"
  python tools/rank_jobs.py notion --platform ashby --keywords "AI,ML" --location "la"
  python tools/rank_jobs.py --file data/job_postings/andurilindustries_20260330_jobs.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.fetch_jobs import (
    LA_METRO_LOCATIONS,
    fetch_ashby,
    fetch_eightfold,
    fetch_greenhouse,
    fetch_lever,
    fetch_talentbrew,
    filter_jobs,
    hydrate_ashby_jobs,
    hydrate_eightfold_jobs,
    hydrate_talentbrew_jobs,
    is_explicitly_foreign_location,
    is_us_compatible_remote_or_hybrid,
    normalize_location_text,
)
from tools.parse_job import parse_job_posting

# ── Profile: personalize via profile/ranking_profile.json ───────────────────
#
# These are GENERIC defaults so the tool works on first clone. Onboarding writes
# profile/ranking_profile.json from your CV to override any of these keys:
#   skills, experience_keywords, target_seniority, years_experience,
#   direct_role_signals, builder_role_signals
# Anything you omit keeps the default below.

_DEFAULTS = {
    "skills": [
        # AI / ML
        "python", "pytorch", "tensorflow", "rag", "llm", "machine learning",
        "deep learning", "nlp", "computer vision", "multi-agent", "agentic",
        "prompt engineering", "fine-tuning", "transformer", "multimodal",
        # Cloud & infra
        "gcp", "aws", "azure", "docker", "kubernetes", "ci/cd", "terraform",
        # Web / full stack
        "typescript", "javascript", "react", "next.js", "fastapi", "node.js",
        "tailwind", "sql", "nosql", "postgres", "mongodb",
        # Tooling
        "git", "rest api", "graphql",
    ],
    "experience_keywords": [
        "production", "deploy", "shipping", "saas", "enterprise", "stakeholder",
        "leadership", "mentor", "architect", "end-to-end", "full stack",
        "startup", "team lead", "scrum", "agile", "optimization", "scale",
        "rag pipeline", "multi-agent", "orchestration", "benchmark", "evaluation",
    ],
    "target_seniority": ["senior", "lead", "staff+", "mid"],
    "years_experience": 5,
    "direct_role_signals": [
        "ai engineer", "artificial intelligence", "machine learning engineer",
        "ml engineer", "applied ai", "generative ai", "llm", "rag", "agentic",
        "prompt engineer", "data scientist", "research engineer", "mlops",
    ],
    "builder_role_signals": [
        "software engineer", "full stack", "full-stack", "developer",
        "solutions architect", "solution architect", "architect",
        "forward deployed", "technical lead", "founding engineer",
        "platform engineer",
    ],
}


def _load_profile() -> dict:
    """Load profile/ranking_profile.json over the generic defaults."""
    cfg = {k: (set(v) if isinstance(v, list) and k not in ("years_experience",) else v)
           for k, v in _DEFAULTS.items()}
    path = PROJECT_ROOT / "profile" / "ranking_profile.json"
    if path.exists():
        try:
            user = json.loads(path.read_text())
            for k, v in user.items():
                if k == "years_experience":
                    cfg[k] = v
                elif isinstance(v, list):
                    cfg[k] = set(x.lower() for x in v)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: could not read {path}: {e}", file=sys.stderr)
    return cfg


_PROFILE = _load_profile()
PROFILE_SKILLS = _PROFILE["skills"]
PROFILE_EXPERIENCE_KEYWORDS = _PROFILE["experience_keywords"]
TARGET_SENIORITY = _PROFILE["target_seniority"]
YEARS_EXPERIENCE = _PROFILE["years_experience"]
DIRECT_ROLE_SIGNALS = _PROFILE["direct_role_signals"]
BUILDER_ROLE_SIGNALS = _PROFILE["builder_role_signals"]


def normalize(text: str) -> str:
    return text.lower().strip()


def score_skill_match(job_skills: list[str], job_text: str) -> tuple[float, list[str], list[str]]:
    """Score skill overlap. Returns (score 0-1, matched, missing)."""
    if not job_skills and not job_text:
        return 0.5, [], []  # No data — neutral

    # Check both explicit skills and full text
    text_lower = job_text.lower()
    matched = []
    checked = set()

    for skill in job_skills:
        s = normalize(skill)
        if s in checked:
            continue
        checked.add(s)
        if any(normalize(ps) == s or s in normalize(ps) or normalize(ps) in s for ps in PROFILE_SKILLS):
            matched.append(skill)

    # Also check profile skills against full job text (word boundary match)
    matched_lower = {normalize(m) for m in matched}
    for ps in PROFILE_SKILLS:
        if ps not in matched_lower:
            # Use word boundary for short terms to avoid false positives
            if len(ps) <= 4:
                pattern = r'\b' + re.escape(ps) + r'\b'
                if re.search(pattern, text_lower, re.IGNORECASE):
                    matched.append(ps)
            elif ps in text_lower:
                matched.append(ps)

    total_job_skills = max(len(checked), 1)
    missing = [s for s in checked if s not in [normalize(m) for m in matched]]

    # Cap the denominator so long enterprise skill lists do not suppress broad compatibility.
    effective_skill_count = max(min(total_job_skills, 8), 4)
    score = min(len(matched) / effective_skill_count, 1.0)
    return score, matched, list(missing)


def score_role_alignment(title: str, job_text: str) -> tuple[float, list[str]]:
    """Score alignment to target AI/builder role families without requiring exact title matches."""
    title_lower = title.lower()
    text_lower = job_text.lower()
    hits = []
    score = 0.0

    direct_title_hits = [signal for signal in DIRECT_ROLE_SIGNALS if signal in title_lower]
    builder_title_hits = [signal for signal in BUILDER_ROLE_SIGNALS if signal in title_lower]
    direct_text_hits = [signal for signal in DIRECT_ROLE_SIGNALS if signal in text_lower]
    builder_text_hits = [signal for signal in BUILDER_ROLE_SIGNALS if signal in text_lower]

    if direct_title_hits:
        score += 0.55
        hits.extend(direct_title_hits)
    if builder_title_hits:
        score += 0.20
        hits.extend(builder_title_hits)
    if direct_text_hits:
        score += 0.15
        hits.extend(direct_text_hits)
    if builder_text_hits:
        score += 0.10
        hits.extend(builder_text_hits)

    deduped_hits = list(dict.fromkeys(hits))
    if not deduped_hits:
        return 0.25, []
    return min(score, 1.0), deduped_hits


def score_experience_alignment(job_text: str) -> tuple[float, list[str]]:
    """Score how well the job aligns with profile experience."""
    text_lower = job_text.lower()
    hits = []
    for kw in PROFILE_EXPERIENCE_KEYWORDS:
        if len(kw) <= 4:
            if re.search(r'\b' + re.escape(kw) + r'\b', text_lower):
                hits.append(kw)
        elif kw in text_lower:
            hits.append(kw)
    score = min(len(hits) / 8, 1.0)  # 8+ keyword hits = perfect score
    return score, hits


def score_seniority(job_seniority: str) -> float:
    """Score seniority fit."""
    if job_seniority in TARGET_SENIORITY:
        return 1.0
    if job_seniority == "junior":
        return 0.2
    return 0.5


def score_location(job_location: str) -> float:
    """Score location fit."""
    loc_normalized = normalize_location_text(job_location)
    if any(alias in loc_normalized for alias in LA_METRO_LOCATIONS):
        return 1.0
    if is_us_compatible_remote_or_hybrid(loc_normalized):
        return 0.95
    if is_explicitly_foreign_location(loc_normalized):
        return 0.0
    if "california" in loc_normalized:
        return 0.75
    if "united states" in loc_normalized or re.search(r"\bu s a?\b", loc_normalized):
        return 0.35
    return 0.1


def score_clearance(clearance_required: bool) -> float:
    """Clearance is a minor differentiator, not a primary driver.
    Defense roles are a backup — don't boost them disproportionately."""
    return 0.7 if clearance_required else 0.5


def compute_overall_score(scores: dict) -> float:
    """Weighted overall score using the same normalized dimensions across companies."""
    weights = {
        "skill_match": 0.30,
        "role_alignment": 0.25,
        "experience": 0.20,
        "seniority": 0.10,
        "location": 0.15,
    }
    return sum(scores[k] * weights[k] for k in weights)


def rank_single_job(parsed: dict) -> dict:
    """Score a single parsed job."""
    full_text = parsed.get("full_text", "")

    skill_score, matched_skills, missing_skills = score_skill_match(
        parsed.get("skills_mentioned", []), full_text
    )
    role_score, role_hits = score_role_alignment(parsed.get("title", ""), full_text)
    exp_score, exp_hits = score_experience_alignment(full_text)
    sen_score = score_seniority(parsed.get("seniority", "mid"))
    loc_score = score_location(parsed.get("location", ""))
    clr_score = score_clearance(parsed.get("clearance_required", False))

    scores = {
        "skill_match": skill_score,
        "role_alignment": role_score,
        "experience": exp_score,
        "seniority": sen_score,
        "location": loc_score,
        "clearance": clr_score,
    }
    overall = compute_overall_score(scores)

    return {
        "title": parsed["title"],
        "company": parsed.get("company", ""),
        "location": parsed.get("location", ""),
        "url": parsed.get("url", ""),
        "seniority": parsed.get("seniority", ""),
        "salary": parsed.get("salary"),
        "clearance_required": parsed.get("clearance_required", False),
        "overall_score": round(overall, 3),
        "scores": {k: round(v, 3) for k, v in scores.items()},
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "role_hits": role_hits,
        "experience_hits": exp_hits,
    }


def rank_jobs_from_listings(
    slug: str,
    platform: str = "greenhouse",
    keywords: list[str] | None = None,
    location: str | None = None,
    top_n: int | None = 20,
) -> list[dict]:
    """Fetch, parse, and rank jobs from a company."""
    # Fetch with content
    print(f"Fetching jobs from {platform}/{slug} (with content)...", file=sys.stderr)
    if platform == "greenhouse":
        jobs = fetch_greenhouse(slug, include_content=True)
    elif platform == "lever":
        jobs = fetch_lever(slug)
    elif platform == "eightfold":
        jobs = fetch_eightfold(slug, include_content=False)
    elif platform == "ashby":
        jobs = fetch_ashby(slug, include_content=False)
    elif platform == "talentbrew":
        jobs = fetch_talentbrew(slug, include_content=False)
    else:
        raise ValueError(f"Unknown platform: {platform}")

    # Deduplicate by title + company + URL
    seen = set()
    deduped = []
    for job in jobs:
        key = (job.get("title", "").lower(), slug.lower(), job.get("url", ""))
        if key not in seen:
            seen.add(key)
            deduped.append(job)
    jobs = deduped

    print(f"Fetched {len(jobs)} total jobs.", file=sys.stderr)

    # Pre-filter by keywords and location
    filtered = filter_jobs(jobs, keywords=keywords, location=location)
    print(f"After filtering: {len(filtered)} jobs.", file=sys.stderr)

    if platform == "eightfold" and filtered:
        print(f"Hydrating {len(filtered)} Eightfold job pages...", file=sys.stderr)
        filtered = hydrate_eightfold_jobs(filtered)
    elif platform == "ashby" and filtered:
        print(f"Hydrating {len(filtered)} Ashby job pages...", file=sys.stderr)
        filtered = hydrate_ashby_jobs(filtered)
    elif platform == "talentbrew" and filtered:
        print(f"Hydrating {len(filtered)} TalentBrew job pages...", file=sys.stderr)
        filtered = hydrate_talentbrew_jobs(filtered)

    # Parse and rank each
    ranked = []
    for i, job in enumerate(filtered):
        parsed = parse_job_posting(
            content_html=job["content_html"],
            title=job["title"],
            company=slug,
            location=job["location"],
            url=job["url"],
            job_id=job["id"],
        )
        result = rank_single_job(parsed)
        ranked.append(result)
        if (i + 1) % 25 == 0:
            print(f"  Ranked {i+1}/{len(filtered)}...", file=sys.stderr)

    ranked.sort(key=lambda r: r["overall_score"], reverse=True)
    if top_n is None:
        return ranked
    return ranked[:top_n]


def print_ranked_table(ranked: list[dict]):
    """Print ranked jobs as a table."""
    if not ranked:
        print("No jobs to rank.")
        return

    print(f"\n{'#':<4} {'Score':<7} {'Title':<45} {'Location':<28} {'Salary':<14} {'Skills':<8} {'Exp':<5} {'Clr'}")
    print("-" * 130)
    for i, r in enumerate(ranked, 1):
        s = r["scores"]
        salary = r["salary"] or "-"
        clr = "Y" if r["clearance_required"] else ""
        print(
            f"{i:<4} {r['overall_score']:<7.3f} {r['title'][:44]:<45} "
            f"{r['location'][:27]:<28} {salary[:13]:<14} "
            f"{s['skill_match']:<8.2f} {s['experience']:<5.2f} {clr}"
        )

    print(f"\nTop {len(ranked)} jobs ranked by overall fit score.")
    print("Score weights: Skills 30% | Role 25% | Experience 20% | Seniority 10% | Location 15%")


def print_job_detail(r: dict):
    """Print detailed scoring for a single job."""
    print(f"\n  {r['title']} @ {r['company']}")
    print(f"  {r['url']}")
    print(f"  Overall: {r['overall_score']:.3f} | Salary: {r['salary'] or 'N/A'}")
    s = r["scores"]
    print(f"  Skills: {s['skill_match']:.2f} | Role: {s['role_alignment']:.2f} | Exp: {s['experience']:.2f} | Seniority: {s['seniority']:.2f} | Location: {s['location']:.2f} | Clearance: {s['clearance']:.2f}")
    if r["matched_skills"]:
        print(f"  Matched skills: {', '.join(r['matched_skills'][:15])}")
    if r["missing_skills"]:
        print(f"  Missing skills: {', '.join(r['missing_skills'][:10])}")
    if r["role_hits"]:
        print(f"  Role hits: {', '.join(r['role_hits'][:10])}")
    if r["experience_hits"]:
        print(f"  Experience hits: {', '.join(r['experience_hits'][:10])}")


def main():
    parser = argparse.ArgumentParser(description="Rank jobs against CV profile")
    parser.add_argument("slug", nargs="?", help="Company slug")
    parser.add_argument("--platform", "-p", choices=["greenhouse", "lever", "eightfold", "ashby", "talentbrew"], default="greenhouse")
    parser.add_argument("--keywords", "-k", help="Comma-separated keywords to pre-filter")
    parser.add_argument("--location", "-l", help="Location filter")
    parser.add_argument("--top", "-n", type=int, default=20, help="Number of top results (default: 20)")
    parser.add_argument("--detail", "-d", action="store_true", help="Show detailed scoring for each job")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--save", "-s", action="store_true", help="Save results to data/")
    args = parser.parse_args()

    if not args.slug:
        parser.print_help()
        sys.exit(1)

    keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else None

    ranked = rank_jobs_from_listings(
        slug=args.slug,
        platform=args.platform,
        keywords=keywords,
        location=args.location,
        top_n=args.top,
    )

    if args.json:
        json.dump(ranked, sys.stdout, indent=2)
    elif args.detail:
        print_ranked_table(ranked)
        print("\n" + "=" * 70)
        print("  DETAILED SCORING")
        print("=" * 70)
        for r in ranked:
            print_job_detail(r)
    else:
        print_ranked_table(ranked)

    if args.save:
        outdir = PROJECT_ROOT / "data"
        outfile = outdir / f"{args.slug}_ranked.json"
        with open(outfile, "w") as f:
            json.dump(ranked, f, indent=2)
        print(f"\nSaved to {outfile}", file=sys.stderr)


if __name__ == "__main__":
    main()
