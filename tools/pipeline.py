#!/usr/bin/env python3
"""
End-to-end job application pipeline.

Scans target companies, fetches jobs, parses, ranks, and outputs a prioritized list.

Usage:
  python tools/pipeline.py scan                    # Scan all target companies
  python tools/pipeline.py scan --company anduril   # Scan one company
  python tools/pipeline.py add <name> <slug> <platform> [--careers-url URL]
  python tools/pipeline.py add CACI searchcareers.caci.com eightfold --careers-url https://searchcareers.caci.com/careers?domain=caci.com
  python tools/pipeline.py add Notion notion ashby --careers-url https://www.notion.so/careers
  python tools/pipeline.py list                    # List tracked companies
  python tools/pipeline.py report                  # Show latest ranked results
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = PROJECT_ROOT / "data"
COMPANIES_FILE = DATA_DIR / "companies.json"
RESULTS_DIR = DATA_DIR / "scan_results"
SUPPORTED_SCAN_PLATFORMS = {"greenhouse", "lever", "eightfold", "ashby", "talentbrew"}

# Default keyword filters for relevant roles
DEFAULT_KEYWORDS = [
    "AI", "machine learning", "ML", "software engineer", "LLM",
    "generative", "generative AI", "applied ai", "prompt engineer",
    "research engineer", "data scientist", "data engineer", "full stack",
    "platform", "infrastructure", "deep learning", "NLP", "solutions architect",
    "solution architect", "agentic",
]

# Known company sources for supported ATS platforms and manual tracking
KNOWN_COMPANIES = {
    # Greenhouse
    "anthropic": {"slug": "anthropic", "platform": "greenhouse", "careers_url": "https://www.anthropic.com/careers"},
    "anduril": {"slug": "andurilindustries", "platform": "greenhouse", "careers_url": "https://www.anduril.com/careers"},
    "scaleai": {"slug": "scaleai", "platform": "greenhouse", "careers_url": "https://scale.com/careers"},
    "openai": {"slug": "", "platform": "manual", "careers_url": "https://openai.com/careers"},
    "datadog": {"slug": "datadog", "platform": "greenhouse", "careers_url": "https://careers.datadoghq.com"},
    "figma": {"slug": "figma", "platform": "greenhouse", "careers_url": "https://www.figma.com/careers"},
    "stripe": {"slug": "stripe", "platform": "greenhouse", "careers_url": "https://stripe.com/jobs"},
    "databricks": {"slug": "databricks", "platform": "greenhouse", "careers_url": "https://www.databricks.com/company/careers"},
    "discord": {"slug": "discord", "platform": "greenhouse", "careers_url": "https://discord.com/careers"},
    "coinbase": {"slug": "coinbase", "platform": "greenhouse", "careers_url": "https://www.coinbase.com/careers"},
    "verkada": {"slug": "verkada", "platform": "greenhouse", "careers_url": "https://www.verkada.com/careers"},
    # Lever
    "palantir": {"slug": "palantir", "platform": "lever", "careers_url": "https://www.palantir.com/careers"},
    "spotify": {"slug": "spotify", "platform": "lever", "careers_url": "https://www.lifeatspotify.com/jobs"},
    "netflix": {"slug": "netflix", "platform": "lever", "careers_url": "https://jobs.netflix.com"},
    # Ashby
    "notion": {"slug": "notion", "platform": "ashby", "careers_url": "https://www.notion.so/careers"},
    "ramp": {"slug": "ramp", "platform": "ashby", "careers_url": "https://ramp.com/careers"},
    # Eightfold
    "caci": {"slug": "searchcareers.caci.com", "platform": "eightfold", "careers_url": "https://searchcareers.caci.com/careers?domain=caci.com"},
}


def load_companies() -> dict:
    if COMPANIES_FILE.exists():
        with open(COMPANIES_FILE) as f:
            return json.load(f)
    return {"companies": []}


def save_companies(data: dict):
    with open(COMPANIES_FILE, "w") as f:
        json.dump(data, f, indent=2)


def add_company(name: str, slug: str, platform: str, careers_url: str = "", roles: list[str] | None = None):
    """Add a company to tracking."""
    data = load_companies()
    # Check if already exists
    for c in data["companies"]:
        if c["name"].lower() == name.lower():
            print(f"Company '{name}' already tracked. Updating.", file=sys.stderr)
            c["slug"] = slug
            c["platform"] = platform
            if careers_url:
                c["careers_url"] = careers_url
            if roles:
                c["roles_of_interest"] = roles
            c["last_checked"] = datetime.now().strftime("%Y-%m-%d")
            save_companies(data)
            return

    entry = {
        "name": name,
        "slug": slug,
        "platform": platform,
        "careers_url": careers_url,
        "notes": "",
        "pay_range": None,
        "roles_of_interest": roles or [],
        "last_checked": datetime.now().strftime("%Y-%m-%d"),
    }
    data["companies"].append(entry)
    save_companies(data)
    print(f"Added '{name}' ({platform}/{slug})", file=sys.stderr)


def list_companies():
    data = load_companies()
    if not data["companies"]:
        print("No companies tracked. Use 'pipeline.py add' or 'pipeline.py seed' to add some.")
        return
    print(f"\n{'#':<4} {'Company':<20} {'Platform':<12} {'Slug':<25} {'Last Checked'}")
    print("-" * 80)
    for i, c in enumerate(data["companies"], 1):
        print(f"{i:<4} {c['name']:<20} {c.get('platform','?'):<12} {c.get('slug','?'):<25} {c.get('last_checked','never')}")


def seed_companies():
    """Seed the companies list with known tech companies."""
    data = load_companies()
    existing = {c["name"].lower() for c in data["companies"]}
    added = 0
    for name, info in KNOWN_COMPANIES.items():
        display_name = name.capitalize()
        if display_name.lower() not in existing:
            data["companies"].append({
                "name": display_name,
                "slug": info["slug"],
                "platform": info["platform"],
                "careers_url": info["careers_url"],
                "notes": "",
                "pay_range": None,
                "roles_of_interest": [],
                "last_checked": None,
            })
            added += 1
    save_companies(data)
    print(f"Seeded {added} companies. Total: {len(data['companies'])}")


def scan_company(company: dict, keywords: list[str], location: str | None) -> tuple[list[dict], str | None]:
    """Scan a single company and return ranked results plus any skip/error reason."""
    from tools.rank_jobs import rank_jobs_from_listings

    slug = company.get("slug", "")
    platform = company.get("platform", "greenhouse")
    if not slug:
        reason = "no slug configured"
        print(f"  Skipping {company['name']}: {reason}", file=sys.stderr)
        return [], reason
    if platform not in SUPPORTED_SCAN_PLATFORMS:
        reason = f"platform '{platform}' is not supported by the automated scanner"
        print(f"  Skipping {company['name']}: {reason}", file=sys.stderr)
        return [], reason

    try:
        ranked = rank_jobs_from_listings(
            slug=slug,
            platform=platform,
            keywords=keywords,
            location=location,
            top_n=None,
        )
        # Tag with company name; apply defense penalty
        is_defense = company.get("defense", False)
        for r in ranked:
            r["company"] = company["name"]
            if is_defense:
                r["overall_score"] = round(r["overall_score"] - 0.05, 3)
                r["defense_penalty"] = True
        return ranked, None
    except Exception as e:
        reason = str(e)
        print(f"  Error scanning {company['name']}: {reason}", file=sys.stderr)
        return [], reason


def scan_all(company_filter: str | None = None, keywords: list[str] | None = None, location: str | None = None, top_n: int = 25):
    """Scan all (or one) tracked companies."""
    data = load_companies()
    companies = data["companies"]
    if not companies:
        print("No companies to scan. Run 'pipeline.py seed' first.")
        return

    if company_filter:
        companies = [c for c in companies if company_filter.lower() in c["name"].lower()]
        if not companies:
            print(f"No company matching '{company_filter}' found.")
            return

    kw = keywords or DEFAULT_KEYWORDS
    loc = location or "la"
    all_ranked = []
    company_status = []

    for company in companies:
        print(f"\n--- Scanning {company['name']} ---", file=sys.stderr)
        results, issue = scan_company(company, kw, loc)
        all_ranked.extend(results)
        company_status.append({
            "name": company["name"],
            "platform": company.get("platform", ""),
            "slug": company.get("slug", ""),
            "result_count": len(results),
            "status": "ok" if issue is None else ("error" if results else "skipped"),
            "issue": issue,
        })

        # Update last_checked
        company["last_checked"] = datetime.now().strftime("%Y-%m-%d")

    save_companies(data)

    # Sort all results by score
    all_ranked.sort(key=lambda r: r["overall_score"], reverse=True)
    top = all_ranked[:top_n]

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = RESULTS_DIR / f"scan_{timestamp}.json"
    companies_scanned = [company["name"] for company in companies]
    companies_with_results = sorted({result["company"] for result in all_ranked})
    skipped_companies = [entry for entry in company_status if entry["issue"]]
    with open(outfile, "w") as f:
        json.dump(
            {
                "scanned_at": datetime.now(timezone.utc).isoformat(),
                "scan_scope": "company" if company_filter else "all",
                "company_filter": company_filter,
                "location": location,
                "keywords": kw,
                "companies_scanned": companies_scanned,
                "companies_with_results": companies_with_results,
                "company_status": company_status,
                "skipped_companies": skipped_companies,
                "total_results": len(all_ranked),
                "all_results": all_ranked,
                "top_results": top,
                "results": top,
            },
            f,
            indent=2,
        )

    # Print results
    print(f"\n{'='*130}")
    print(f"  TOP {len(top)} JOBS ACROSS ALL SCANNED COMPANIES")
    print(f"{'='*130}")
    print(f"\n{'#':<4} {'Score':<7} {'Company':<16} {'Title':<40} {'Location':<25} {'Salary':<14} {'Clr'}")
    print("-" * 130)
    for i, r in enumerate(top, 1):
        salary = r.get("salary") or "-"
        clr = "Y" if r.get("clearance_required") else ""
        print(
            f"{i:<4} {r['overall_score']:<7.3f} {r['company'][:15]:<16} "
            f"{r['title'][:39]:<40} {r['location'][:24]:<25} {salary[:13]:<14} {clr}"
        )

    print(f"\nResults saved to {outfile}")
    print(f"Total jobs scanned across all companies: {len(all_ranked)}")
    return top


def show_report():
    """Show the latest scan results."""
    if not RESULTS_DIR.exists():
        print("No scan results found. Run 'pipeline.py scan' first.")
        return

    files = sorted(RESULTS_DIR.glob("scan_*.json"), reverse=True)
    if not files:
        print("No scan results found.")
        return

    latest = files[0]
    with open(latest) as f:
        data = json.load(f)

    print(f"\nLatest scan: {data['scanned_at']}")
    print(f"Total results: {data['total_results']}")

    top = data["top_results"]
    print(f"\n{'#':<4} {'Score':<7} {'Company':<16} {'Title':<40} {'Location':<25} {'Salary':<14} {'Clr'}")
    print("-" * 130)
    for i, r in enumerate(top, 1):
        salary = r.get("salary") or "-"
        clr = "Y" if r.get("clearance_required") else ""
        print(
            f"{i:<4} {r['overall_score']:<7.3f} {r['company'][:15]:<16} "
            f"{r['title'][:39]:<40} {r['location'][:24]:<25} {salary[:13]:<14} {clr}"
        )


def main():
    parser = argparse.ArgumentParser(description="Job application pipeline")
    sub = parser.add_subparsers(dest="command")

    # scan
    scan_p = sub.add_parser("scan", help="Scan companies for matching jobs")
    scan_p.add_argument("--company", "-c", help="Filter to one company")
    scan_p.add_argument("--keywords", "-k", help="Override keyword filter (comma-separated)")
    scan_p.add_argument("--location", "-l", default="la", help="Location filter (default: la)")
    scan_p.add_argument("--top", "-n", type=int, default=25, help="Number of top results")

    # add
    add_p = sub.add_parser("add", help="Add a company to tracking")
    add_p.add_argument("name", help="Company display name")
    add_p.add_argument("slug", help="ATS slug")
    add_p.add_argument("platform", choices=["greenhouse", "lever", "eightfold", "ashby", "talentbrew", "manual"], help="ATS platform")
    add_p.add_argument("--careers-url", default="", help="Careers page URL")

    # list
    sub.add_parser("list", help="List tracked companies")

    # seed
    sub.add_parser("seed", help="Seed with known tech companies")

    # report
    sub.add_parser("report", help="Show latest scan results")

    args = parser.parse_args()

    if args.command == "scan":
        kw = [k.strip() for k in args.keywords.split(",")] if args.keywords else None
        scan_all(company_filter=args.company, keywords=kw, location=args.location, top_n=args.top)
    elif args.command == "add":
        add_company(args.name, args.slug, args.platform, args.careers_url)
    elif args.command == "list":
        list_companies()
    elif args.command == "seed":
        seed_companies()
    elif args.command == "report":
        show_report()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
