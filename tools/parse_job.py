#!/usr/bin/env python3
"""
Parse job descriptions into structured data.

Extracts sections, requirements, skills, and metadata from job posting HTML.

Usage:
  python tools/parse_job.py <company_slug> <job_id> --platform greenhouse
  python tools/parse_job.py searchcareers.caci.com 1443149827039 --platform eightfold
  python tools/parse_job.py notion c7f6dbf1-5637-45c5-8495-57a65f1061d2 --platform ashby
  python tools/parse_job.py --url <job_posting_url>
  python tools/parse_job.py --file data/job_postings/some_job.json
"""

import argparse
import html as html_mod
import json
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Tag

PROJECT_ROOT = Path(__file__).resolve().parent.parent


HEADING_MAP = [
    (["ABOUT THE JOB", "THE ROLE", "JOB DESCRIPTION", "OVERVIEW", "POSITION SUMMARY"], "description"),
    (["WHAT YOU", "RESPONSIBILITIES", "YOU WILL", "YOU'LL DO", "KEY RESPONSIBILITIES", "IN THIS ROLE"], "responsibilities"),
    (["REQUIRED", "QUALIFICATIONS", "REQUIREMENTS", "WHAT WE NEED", "MUST HAVE", "MINIMUM", "WHAT WE'RE LOOKING"], "requirements"),
    (["PREFERRED", "NICE TO HAVE", "BONUS", "DESIRED", "PLUS"], "preferred"),
    (["ABOUT THE TEAM", "THE TEAM", "ABOUT US"], "about_team"),
    (["COMPENSATION", "SALARY", "PAY", "BENEFITS", "PERKS"], "compensation"),
    (["ABOUT THE COMPANY", "ABOUT ANDURIL", "ABOUT ANTHROPIC", "ABOUT GOOGLE", "WHO WE ARE"], "about_company"),
]


def classify_heading(text: str) -> str | None:
    """Classify a heading text into a section name."""
    text_upper = text.upper().strip()
    for keywords, section_name in HEADING_MAP:
        if any(kw in text_upper for kw in keywords):
            return section_name
    return None


def html_to_sections(raw_html: str) -> dict:
    """Parse job HTML into labeled sections."""
    # Unescape HTML entities in case content is double-encoded
    unescaped = html_mod.unescape(raw_html)
    soup = BeautifulSoup(unescaped, "html.parser")

    sections = {}
    current_section = "intro"
    current_parts = []

    # Walk through top-level and nested block elements
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "strong", "b", "p", "ul", "ol", "li", "div"]):
        if tag.name in ("h1", "h2", "h3", "h4", "h5"):
            heading_text = tag.get_text(strip=True)
            section = classify_heading(heading_text)
            if section:
                if current_parts:
                    sections[current_section] = "\n".join(current_parts).strip()
                current_section = section
                current_parts = []
                continue
        elif tag.name in ("strong", "b"):
            heading_text = tag.get_text(strip=True)
            section = classify_heading(heading_text)
            if section and tag.parent and tag.parent.name in ("p", "div", "h4", "h3"):
                if current_parts:
                    sections[current_section] = "\n".join(current_parts).strip()
                current_section = section
                current_parts = []
                continue

        # Only collect text from leaf-ish elements
        if tag.name in ("p", "li"):
            text = tag.get_text(strip=True)
            if text:
                current_parts.append(text)

    # Save final section
    if current_parts:
        sections[current_section] = "\n".join(current_parts).strip()

    # Fallback
    if not sections or (len(sections) == 1 and "intro" in sections):
        full_text = soup.get_text(separator="\n", strip=True)
        sections["full_text"] = full_text

    return sections


def extract_bullet_points(raw_html: str, section_keywords: list[str]) -> list[str]:
    """Extract bullet points from sections matching keywords."""
    unescaped = html_mod.unescape(raw_html)
    soup = BeautifulSoup(unescaped, "html.parser")
    bullets = []
    capture = False

    for elem in soup.find_all(["h1", "h2", "h3", "h4", "h5", "strong", "b", "li"]):
        if elem.name in ("h1", "h2", "h3", "h4", "h5", "strong", "b"):
            text = elem.get_text(strip=True).upper()
            if any(kw in text for kw in section_keywords):
                capture = True
            elif classify_heading(text) is not None:
                # Hit a different known section — stop capturing
                capture = False
        elif capture and elem.name == "li":
            bullet_text = elem.get_text(strip=True)
            if bullet_text and len(bullet_text) > 10:
                bullets.append(bullet_text)

    return bullets


def extract_skills_from_text(text: str) -> list[str]:
    """Extract technical skills mentioned in text using pattern matching."""
    skill_patterns = [
        # Languages & frameworks
        r'\bPython\b', r'\bTypeScript\b', r'\bJavaScript\b', r'\bJava\b', r'\bGo\b(?:lang)?',
        r'\bRust\b', r'\bC\+\+\b', r'\bC#\b', r'\bRuby\b', r'\bScala\b', r'\bKotlin\b',
        r'\bSwift\b', r'\bR\b(?:\s+programming)?',
        # AI/ML
        r'\bPyTorch\b', r'\bTensorFlow\b', r'\bJAX\b', r'\bscikit-learn\b',
        r'\bLangChain\b', r'\bLlamaIndex\b', r'\bHugging\s*Face\b',
        r'\bRAG\b', r'\bLLM\b', r'\bNLP\b', r'\bcomputer vision\b',
        r'\btransformer\b', r'\bfine-tun(?:e|ing)\b', r'\bGPT\b', r'\bGemini\b',
        r'\bClaude\b', r'\bvLLM\b', r'\bMLOps\b', r'\bMLflow\b',
        r'\bdeep learning\b', r'\bmachine learning\b', r'\breinforcement learning\b',
        r'\bmulti-agent\b', r'\bagentic\b', r'\bprompt engineering\b',
        # Cloud & infra
        r'\bAWS\b', r'\bGCP\b', r'\bAzure\b', r'\bKubernetes\b', r'\bDocker\b',
        r'\bTerraform\b', r'\bCI/CD\b', r'\bVertex AI\b', r'\bSageMaker\b',
        r'\bBedrock\b', r'\bFirebase\b', r'\bFirestore\b',
        # Data
        r'\bSQL\b', r'\bNoSQL\b', r'\bMongoDB\b', r'\bPostgreSQL\b', r'\bRedis\b',
        r'\bSpark\b', r'\bKafka\b', r'\bAirflow\b', r'\bSnowflake\b', r'\bBigQuery\b',
        # Web
        r'\bReact\b', r'\bNext\.js\b', r'\bNode\.js\b', r'\bFastAPI\b', r'\bFlask\b',
        r'\bDjango\b', r'\bGraphQL\b', r'\bREST\b',
        # Security / Gov
        r'\b(?:Secret|TS/SCI|Top Secret)\s*(?:Clearance)?\b',
        r'\bair[- ]gapped\b', r'\bFedRAMP\b', r'\bSTIG\b',
    ]

    found = set()
    for pattern in skill_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            found.add(m.strip())
    return sorted(found, key=str.lower)


def extract_salary(text: str) -> str | None:
    """Extract salary range from text."""
    patterns = [
        r'\$[\d,]+(?:\s*[-–]\s*\$?[\d,]+)?(?:\s*(?:per year|annually|/yr|/year))?',
        r'[\d,]+[kK]\s*[-–]\s*[\d,]+[kK]',
        r'USD\s*[\d,]+\s*[-–]\s*[\d,]+',
    ]
    for p in patterns:
        match = re.search(p, text)
        if match:
            return match.group(0)
    return None


def parse_job_posting(
    content_html: str,
    title: str = "",
    company: str = "",
    location: str = "",
    url: str = "",
    job_id: str = "",
) -> dict:
    """Parse a job posting into structured data."""
    soup = BeautifulSoup(content_html, "html.parser")
    full_text = soup.get_text(separator="\n", strip=True)

    sections = html_to_sections(content_html)
    responsibilities = extract_bullet_points(content_html, ["WHAT YOU", "RESPONSIBILITIES", "YOU WILL", "YOU'LL DO"])
    requirements = extract_bullet_points(content_html, ["REQUIRED", "QUALIFICATIONS", "REQUIREMENTS", "MUST HAVE", "MINIMUM"])
    preferred = extract_bullet_points(content_html, ["PREFERRED", "NICE TO HAVE", "BONUS", "DESIRED", "PLUS"])
    skills = extract_skills_from_text(full_text)
    salary = extract_salary(full_text)

    # Determine seniority from title
    title_lower = title.lower()
    if any(kw in title_lower for kw in ["principal", "staff", "distinguished", "fellow"]):
        seniority = "staff+"
    elif any(kw in title_lower for kw in ["senior", "sr.", "sr "]):
        seniority = "senior"
    elif any(kw in title_lower for kw in ["lead", "manager", "director", "head", "chief", "vp"]):
        seniority = "lead"
    elif any(kw in title_lower for kw in ["junior", "jr.", "jr ", "associate", "entry"]):
        seniority = "junior"
    else:
        seniority = "mid"

    # Detect clearance requirement
    clearance_required = bool(re.search(r'(?:secret|TS/SCI|top secret|clearance)\b', full_text, re.IGNORECASE))

    return {
        "id": job_id,
        "title": title,
        "company": company,
        "location": location,
        "url": url,
        "seniority": seniority,
        "salary": salary,
        "clearance_required": clearance_required,
        "skills_mentioned": skills,
        "responsibilities": responsibilities,
        "requirements": requirements,
        "preferred": preferred,
        "sections": sections,
        "full_text": full_text,
    }


def fetch_and_parse_greenhouse(slug: str, job_id: str) -> dict:
    """Fetch a Greenhouse job and parse it."""
    sys.path.insert(0, str(PROJECT_ROOT))
    from tools.fetch_jobs import fetch_greenhouse_job_detail
    raw = fetch_greenhouse_job_detail(slug, job_id)
    return parse_job_posting(
        content_html=raw["content_html"],
        title=raw["title"],
        company=raw.get("company_name", slug),
        location=raw["location"],
        url=raw["url"],
        job_id=raw["id"],
    )


def fetch_and_parse_eightfold(slug: str, job_id: str) -> dict:
    """Fetch an Eightfold job and parse it."""
    sys.path.insert(0, str(PROJECT_ROOT))
    from tools.fetch_jobs import fetch_eightfold_job_detail
    raw = fetch_eightfold_job_detail(slug, job_id)
    return parse_job_posting(
        content_html=raw["content_html"],
        title=raw["title"],
        company=slug,
        location=raw["location"],
        url=raw["url"],
        job_id=raw["id"],
    )


def fetch_and_parse_ashby(slug: str, job_id: str) -> dict:
    """Fetch an Ashby job and parse it."""
    sys.path.insert(0, str(PROJECT_ROOT))
    from tools.fetch_jobs import fetch_ashby_job_detail
    raw = fetch_ashby_job_detail(slug, job_id)
    return parse_job_posting(
        content_html=raw["content_html"],
        title=raw["title"],
        company=raw.get("company_name", slug),
        location=raw["location"],
        url=raw["url"],
        job_id=raw["id"],
    )


def fetch_and_parse_talentbrew(slug: str, job_id: str) -> dict:
    """Fetch a TalentBrew job and parse it."""
    sys.path.insert(0, str(PROJECT_ROOT))
    from tools.fetch_jobs import fetch_talentbrew_job_detail
    raw = fetch_talentbrew_job_detail(slug, job_id)
    return parse_job_posting(
        content_html=raw["content_html"],
        title=raw["title"],
        company=slug,
        location=raw["location"],
        url=raw["url"],
        job_id=raw["id"],
    )


def fetch_and_parse_url(url: str) -> dict:
    """Fetch a job posting URL and parse it."""
    resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    title = soup.find("title")
    title_text = title.get_text(strip=True) if title else ""
    return parse_job_posting(
        content_html=resp.text,
        title=title_text,
        url=url,
    )


def save_parsed_job(parsed: dict, filename: str | None = None) -> Path:
    """Save parsed job to data/job_postings/."""
    outdir = PROJECT_ROOT / "data" / "job_postings"
    outdir.mkdir(parents=True, exist_ok=True)
    if not filename:
        company = re.sub(r'[^a-z0-9]', '_', (parsed.get("company") or "unknown").lower())
        title_short = re.sub(r'[^a-z0-9]', '_', parsed["title"].lower())[:40]
        filename = f"{company}_{title_short}.json"
    outfile = outdir / filename
    # Don't save full_text to keep files manageable
    save_data = {k: v for k, v in parsed.items() if k != "full_text"}
    with open(outfile, "w") as f:
        json.dump(save_data, f, indent=2)
    return outfile


def print_parsed_job(parsed: dict):
    """Pretty-print a parsed job."""
    print(f"\n{'='*70}")
    print(f"  {parsed['title']}")
    print(f"  {parsed['company']} | {parsed['location']}")
    print(f"  {parsed['url']}")
    print(f"{'='*70}")
    print(f"\n  Seniority:  {parsed['seniority']}")
    print(f"  Salary:     {parsed['salary'] or 'Not listed'}")
    print(f"  Clearance:  {'Yes' if parsed['clearance_required'] else 'No'}")

    if parsed["skills_mentioned"]:
        print(f"\n  Skills mentioned ({len(parsed['skills_mentioned'])}):")
        # Group into rows of 6
        skills = parsed["skills_mentioned"]
        for i in range(0, len(skills), 6):
            print(f"    {', '.join(skills[i:i+6])}")

    if parsed["responsibilities"]:
        print(f"\n  Responsibilities ({len(parsed['responsibilities'])}):")
        for r in parsed["responsibilities"][:5]:
            print(f"    - {r[:100]}")

    if parsed["requirements"]:
        print(f"\n  Requirements ({len(parsed['requirements'])}):")
        for r in parsed["requirements"][:5]:
            print(f"    - {r[:100]}")

    if parsed["preferred"]:
        print(f"\n  Preferred ({len(parsed['preferred'])}):")
        for r in parsed["preferred"][:5]:
            print(f"    - {r[:100]}")

    print()


def main():
    parser = argparse.ArgumentParser(description="Parse job descriptions into structured data")
    parser.add_argument("slug", nargs="?", help="Company slug on the ATS platform")
    parser.add_argument("job_id", nargs="?", help="Job ID to fetch and parse")
    parser.add_argument("--platform", "-p", choices=["greenhouse", "lever", "eightfold", "ashby", "talentbrew"], default="greenhouse")
    parser.add_argument("--url", "-u", help="Direct URL to a job posting")
    parser.add_argument("--save", "-s", action="store_true", help="Save parsed result to data/job_postings/")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.url:
        print(f"Fetching {args.url}...", file=sys.stderr)
        parsed = fetch_and_parse_url(args.url)
    elif args.slug and args.job_id:
        print(f"Fetching {args.platform}/{args.slug}/{args.job_id}...", file=sys.stderr)
        if args.platform == "greenhouse":
            parsed = fetch_and_parse_greenhouse(args.slug, args.job_id)
        elif args.platform == "eightfold":
            parsed = fetch_and_parse_eightfold(args.slug, args.job_id)
        elif args.platform == "ashby":
            parsed = fetch_and_parse_ashby(args.slug, args.job_id)
        elif args.platform == "talentbrew":
            parsed = fetch_and_parse_talentbrew(args.slug, args.job_id)
        else:
            print("Lever single-job fetch not yet supported. Use --url instead.", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)

    if args.save:
        outfile = save_parsed_job(parsed)
        print(f"Saved to {outfile}", file=sys.stderr)

    if args.json:
        output = {k: v for k, v in parsed.items() if k != "full_text"}
        json.dump(output, sys.stdout, indent=2)
    else:
        print_parsed_job(parsed)


if __name__ == "__main__":
    main()
