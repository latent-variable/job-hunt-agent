#!/usr/bin/env python3
"""
Fetch job listings from company career pages via ATS APIs.

Supported platforms:
  - Greenhouse (boards-api.greenhouse.io)
  - Lever (api.lever.co)
  - Eightfold (public sitemap + job page JobPosting JSON-LD)
  - Ashby (jobs.ashbyhq.com embedded app data)
  - TalentBrew (paginated hosted search pages)

Usage:
  python tools/fetch_jobs.py <company_slug> --platform greenhouse
  python tools/fetch_jobs.py <company_slug> --platform lever
  python tools/fetch_jobs.py searchcareers.caci.com --platform eightfold
  python tools/fetch_jobs.py notion --platform ashby
  python tools/fetch_jobs.py jobs.disneycareers.com --platform talentbrew
  python tools/fetch_jobs.py <company_slug> --platform greenhouse --keywords "AI,ML,engineer" --location "los angeles"
  python tools/fetch_jobs.py <company_slug> --platform greenhouse --save
"""

import argparse
import concurrent.futures
import html as html_mod
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
COMPANIES_FILE = DATA_DIR / "companies.json"
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; JobHuntAgent/1.0; +https://github.com/latent-variable/job-hunt-agent)"
}
ASHBY_BASE_URL = "https://jobs.ashbyhq.com"
REQUEST_TIMEOUT = 30
REQUEST_ATTEMPTS = 3


EIGHTFOLD_COUNTRY_SLUGS = {
    "united-states-of-america": "United States of America",
    "united-kingdom": "United Kingdom",
    "germany": "Germany",
    "canada": "Canada",
    "australia": "Australia",
}

EIGHTFOLD_REGION_SLUGS = {
    "district-of-columbia": "District of Columbia",
    "any-state": "Any State",
    "california": "California",
    "maryland": "Maryland",
    "virginia": "Virginia",
    "texas": "Texas",
    "florida": "Florida",
    "oklahoma": "Oklahoma",
    "north-carolina": "North Carolina",
    "south-carolina": "South Carolina",
    "new-york": "New York",
    "new-jersey": "New Jersey",
    "pennsylvania": "Pennsylvania",
    "illinois": "Illinois",
    "massachusetts": "Massachusetts",
    "colorado": "Colorado",
    "washington": "Washington",
    "georgia": "Georgia",
    "alabama": "Alabama",
    "alaska": "Alaska",
    "arizona": "Arizona",
    "arkansas": "Arkansas",
    "connecticut": "Connecticut",
    "delaware": "Delaware",
    "hawaii": "Hawaii",
    "idaho": "Idaho",
    "indiana": "Indiana",
    "iowa": "Iowa",
    "kansas": "Kansas",
    "kentucky": "Kentucky",
    "louisiana": "Louisiana",
    "maine": "Maine",
    "michigan": "Michigan",
    "minnesota": "Minnesota",
    "mississippi": "Mississippi",
    "missouri": "Missouri",
    "montana": "Montana",
    "nebraska": "Nebraska",
    "nevada": "Nevada",
    "new-hampshire": "New Hampshire",
    "new-mexico": "New Mexico",
    "ohio": "Ohio",
    "oregon": "Oregon",
    "rhode-island": "Rhode Island",
    "south-dakota": "South Dakota",
    "tennessee": "Tennessee",
    "utah": "Utah",
    "vermont": "Vermont",
    "west-virginia": "West Virginia",
    "wisconsin": "Wisconsin",
    "wyoming": "Wyoming",
}


def _http_get(url: str, *, params: dict | None = None, timeout: int = REQUEST_TIMEOUT) -> requests.Response:
    """GET with a small retry budget to smooth over transient ATS timeouts."""
    last_exc: Exception | None = None
    for attempt in range(1, REQUEST_ATTEMPTS + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout, headers=REQUEST_HEADERS)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            last_exc = exc
            if attempt == REQUEST_ATTEMPTS:
                break
            print(
                f"Warning: request attempt {attempt}/{REQUEST_ATTEMPTS} failed for {url}: {exc}",
                file=sys.stderr,
            )
            time.sleep(min(attempt, 3))

    assert last_exc is not None
    raise last_exc


def fetch_greenhouse(slug: str, include_content: bool = False) -> list[dict]:
    """Fetch all jobs from a Greenhouse board."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    params = {"content": "true"} if include_content else {}
    resp = _http_get(url, params=params)
    data = resp.json()
    jobs = data.get("jobs", [])

    results = []
    for j in jobs:
        results.append({
            "id": str(j["id"]),
            "title": j["title"],
            "location": j.get("location", {}).get("name", ""),
            "url": j.get("absolute_url", ""),
            "updated_at": j.get("updated_at", ""),
            "departments": [d["name"] for d in j.get("departments", [])],
            "content_html": html_mod.unescape(j.get("content", "")) if include_content else "",
            "source_platform": "greenhouse",
            "source_slug": slug,
        })
    return results


def fetch_greenhouse_job_detail(slug: str, job_id: str) -> dict:
    """Fetch full details for a single Greenhouse job."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}"
    resp = _http_get(url)
    j = resp.json()
    return {
        "id": str(j["id"]),
        "title": j["title"],
        "location": j.get("location", {}).get("name", ""),
        "url": j.get("absolute_url", ""),
        "updated_at": j.get("updated_at", ""),
        "departments": [d["name"] for d in j.get("departments", [])],
        "offices": [o["name"] for o in j.get("offices", [])],
        "content_html": html_mod.unescape(j.get("content", "")),
        "company_name": j.get("company_name", ""),
        "source_platform": "greenhouse",
        "source_slug": slug,
    }


def fetch_lever(slug: str) -> list[dict]:
    """Fetch all jobs from a Lever board."""
    all_jobs = []
    offset = 0
    limit = 100
    while True:
        url = f"https://api.lever.co/v0/postings/{slug}"
        params = {"limit": limit, "skip": offset, "mode": "json"}
        resp = _http_get(url, params=params)
        data = resp.json()
        if isinstance(data, dict) and data.get("error"):
            raise ValueError(f"Lever API error: {data['error']}")
        if not isinstance(data, list) or len(data) == 0:
            break
        for j in data:
            cats = j.get("categories", {})
            all_jobs.append({
                "id": j["id"],
                "title": j.get("text", ""),
                "location": cats.get("location", ""),
                "url": j.get("hostedUrl", ""),
                "updated_at": "",
                "departments": [cats.get("department", ""), cats.get("team", "")],
                "content_html": j.get("descriptionPlain", j.get("description", "")),
                "source_platform": "lever",
                "source_slug": slug,
            })
        if len(data) < limit:
            break
        offset += limit
    return all_jobs


def _normalize_talentbrew_base(slug: str) -> tuple[str, str]:
    """Return a stable TalentBrew source slug and base URL."""
    candidate = slug.strip().rstrip("/")
    if candidate.startswith("http://") or candidate.startswith("https://"):
        parsed = urlparse(candidate)
        source_slug = parsed.netloc or candidate
        base_url = f"{parsed.scheme}://{parsed.netloc}"
    else:
        source_slug = candidate
        base_url = f"https://{candidate}"
    return source_slug, base_url


def _extract_talentbrew_listing_rows(html: str, base_url: str, source_slug: str) -> tuple[list[dict], int]:
    """Parse a TalentBrew search page into job stubs."""
    soup = BeautifulSoup(html, "html.parser")
    container = soup.select_one("[data-total-pages]")
    total_pages = 1
    if container and container.get("data-total-pages", "").isdigit():
        total_pages = int(container["data-total-pages"])

    jobs = []
    for row in soup.select("#search-results-list tbody tr"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        link = row.select_one("td a[href]")
        if not link:
            continue
        href = link.get("href", "").strip()
        if not href:
            continue
        job_url = urljoin(base_url, href)
        match = re.search(r"/(\d+)(?:\?|$)", job_url)
        job_id = match.group(1) if match else job_url
        title = link.get_text(" ", strip=True)
        updated_at = cells[1].get_text(" ", strip=True)
        brand = cells[2].get_text(" ", strip=True)
        location = cells[3].get_text(" ", strip=True)
        jobs.append({
            "id": str(job_id),
            "title": title,
            "location": location,
            "url": job_url,
            "updated_at": updated_at,
            "departments": [brand] if brand else [],
            "content_html": "",
            "source_platform": "talentbrew",
            "source_slug": source_slug,
            "search_text": " ".join(part for part in [title, brand] if part),
            "location_search_text": location.lower(),
        })
    return jobs, total_pages


def fetch_talentbrew_job_detail(slug: str, job_id: str) -> dict:
    """Fetch full details for a single TalentBrew job."""
    source_slug, base_url = _normalize_talentbrew_base(slug)
    search_url = f"{base_url}/search-jobs"
    total_pages = 1
    page = 1

    while page <= total_pages:
        params = {"p": page} if page > 1 else None
        resp = _http_get(search_url, params=params)
        jobs, discovered_pages = _extract_talentbrew_listing_rows(resp.text, base_url, source_slug)
        total_pages = max(total_pages, discovered_pages)
        for job in jobs:
            if job["id"] != str(job_id):
                continue
            detail_resp = _http_get(job["url"])
            soup = BeautifulSoup(detail_resp.text, "html.parser")
            description = soup.select_one(".job-description")
            location_node = soup.select_one(".job-location-scrape")
            business_node = soup.select_one("#job-brand")
            departments = job["departments"]
            if business_node:
                business_text = business_node.get_text(" ", strip=True).replace("Business", "", 1).strip()
                departments = [business_text] if business_text else departments
            location = location_node.get_text(" ", strip=True) if location_node else job["location"]
            return {
                **job,
                "location": location,
                "departments": departments,
                "content_html": str(description or soup),
                "location_search_text": location.lower(),
            }
        page += 1

    raise ValueError(f"Could not find TalentBrew job id {job_id} for {slug}")


def hydrate_talentbrew_jobs(jobs: list[dict], max_workers: int = 8) -> list[dict]:
    """Fetch full details for a filtered subset of TalentBrew jobs."""
    if not jobs:
        return []

    hydrated: list[dict | None] = [None] * len(jobs)
    workers = min(max_workers, len(jobs))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_index = {
            executor.submit(fetch_talentbrew_job_detail, job.get("source_slug", ""), job["id"]): index
            for index, job in enumerate(jobs)
        }
        for future in concurrent.futures.as_completed(future_to_index):
            index = future_to_index[future]
            try:
                hydrated[index] = future.result()
            except Exception as exc:
                print(f"Warning: failed to hydrate TalentBrew job {jobs[index].get('url', '')}: {exc}", file=sys.stderr)
                hydrated[index] = jobs[index]

    return [job for job in hydrated if job]


def fetch_talentbrew(slug: str, include_content: bool = False) -> list[dict]:
    """Fetch jobs from a TalentBrew-hosted careers site."""
    source_slug, base_url = _normalize_talentbrew_base(slug)
    search_url = f"{base_url}/search-jobs"

    first_page = _http_get(search_url)
    jobs, total_pages = _extract_talentbrew_listing_rows(first_page.text, base_url, source_slug)

    for page in range(2, total_pages + 1):
        resp = _http_get(search_url, params={"p": page})
        page_jobs, _ = _extract_talentbrew_listing_rows(resp.text, base_url, source_slug)
        jobs.extend(page_jobs)

    if include_content:
        return hydrate_talentbrew_jobs(jobs)
    return jobs


def _extract_ashby_app_data(html: str) -> dict:
    """Extract embedded Ashby app data from a hosted jobs page."""
    soup = BeautifulSoup(html, "html.parser")
    prefix = "window.__appData = "
    decoder = json.JSONDecoder()

    for script in soup.find_all("script"):
        text = script.string or script.get_text()
        if prefix not in text:
            continue
        start = text.index(prefix) + len(prefix)
        data, _ = decoder.raw_decode(text[start:])
        return data

    raise ValueError("Could not find embedded Ashby app data")


def _ashby_request(url: str) -> dict:
    resp = _http_get(url)
    return _extract_ashby_app_data(resp.text)


def _ashby_secondary_locations(posting: dict) -> list[str]:
    secondary = posting.get("secondaryLocationNames")
    if isinstance(secondary, list):
        return [item.strip() for item in secondary if isinstance(item, str) and item.strip()]

    secondary = posting.get("secondaryLocations")
    results = []
    if isinstance(secondary, list):
        for item in secondary:
            if isinstance(item, str) and item.strip():
                results.append(item.strip())
            elif isinstance(item, dict):
                name = (item.get("locationName") or item.get("name") or "").strip()
                if name:
                    results.append(name)
    return results


def _ashby_location(posting: dict) -> str:
    primary = (posting.get("locationName") or "").strip()
    workplace = (posting.get("workplaceType") or "").strip()
    secondary = _ashby_secondary_locations(posting)
    base = primary

    if secondary:
        secondary_text = ", ".join(dict.fromkeys(secondary))
        base = f"{primary} ({secondary_text})" if primary else secondary_text

    if workplace:
        return f"{workplace} - {base}" if base else workplace
    if posting.get("isRemote") and not base:
        return "Remote"
    return base


def _ashby_departments(posting: dict) -> list[str]:
    values = [
        posting.get("departmentName", ""),
        posting.get("teamName", ""),
        posting.get("departmentExternalName", ""),
        posting.get("teamExternalName", ""),
    ]
    seen = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return seen


def _build_ashby_stub(slug: str, posting: dict) -> dict:
    location = _ashby_location(posting)
    return {
        "id": posting["id"],
        "title": posting.get("title", ""),
        "location": location,
        "url": f"{ASHBY_BASE_URL}/{slug}/{posting['id']}",
        "updated_at": posting.get("updatedAt", ""),
        "departments": _ashby_departments(posting),
        "content_html": "",
        "source_platform": "ashby",
        "source_slug": slug,
        "search_text": " ".join(
            part for part in [
                posting.get("title", ""),
                posting.get("teamName", ""),
                posting.get("departmentName", ""),
                posting.get("employmentType", ""),
            ]
            if part
        ),
        "location_search_text": location.lower(),
    }


def fetch_ashby_job_detail(slug: str, job_id: str) -> dict:
    """Fetch full details for a single Ashby job."""
    data = _ashby_request(f"{ASHBY_BASE_URL}/{slug}/{job_id}")
    posting = data.get("posting") or data.get("jobPosting")
    if not isinstance(posting, dict):
        raise ValueError(f"Could not find Ashby posting data for {slug}/{job_id}")

    description_html = posting.get("descriptionHtml", "")
    compensation_summary = posting.get("scrapeableCompensationSalarySummary") or posting.get("compensationTierSummary")
    if compensation_summary:
        description_html += f"<p>Compensation: {html_mod.escape(compensation_summary)}</p>"

    return {
        "id": posting["id"],
        "title": posting.get("title", ""),
        "location": _ashby_location(posting),
        "url": f"{ASHBY_BASE_URL}/{slug}/{posting['id']}",
        "updated_at": posting.get("updatedAt", ""),
        "departments": _ashby_departments(posting),
        "content_html": description_html,
        "company_name": data.get("organization", {}).get("name", ""),
        "source_platform": "ashby",
        "source_slug": slug,
        "search_text": posting.get("descriptionPlainText", ""),
        "location_search_text": _ashby_location(posting).lower(),
    }


def hydrate_ashby_jobs(jobs: list[dict], max_workers: int = 12) -> list[dict]:
    """Fetch full details for a filtered subset of Ashby jobs."""
    if not jobs:
        return []

    hydrated: list[dict | None] = [None] * len(jobs)
    workers = min(max_workers, len(jobs))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_index = {
            executor.submit(fetch_ashby_job_detail, job.get("source_slug", ""), job["id"]): index
            for index, job in enumerate(jobs)
        }
        for future in concurrent.futures.as_completed(future_to_index):
            index = future_to_index[future]
            try:
                hydrated[index] = future.result()
            except Exception as exc:
                print(f"Warning: failed to hydrate Ashby job {jobs[index].get('url', '')}: {exc}", file=sys.stderr)
                hydrated[index] = jobs[index]

    return [job for job in hydrated if job]


def fetch_ashby(slug: str, include_content: bool = False) -> list[dict]:
    """Fetch jobs from an Ashby hosted jobs page."""
    data = _ashby_request(f"{ASHBY_BASE_URL}/{slug}")
    job_board = data.get("jobBoard", {})
    postings = job_board.get("jobPostings", [])

    jobs = [
        _build_ashby_stub(slug, posting)
        for posting in postings
        if posting.get("isListed", True)
    ]

    if include_content:
        return hydrate_ashby_jobs(jobs)
    return jobs


def _normalize_eightfold_base(slug: str) -> tuple[str, str]:
    raw = slug.strip().rstrip("/")
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    base_path = parsed.path.rstrip("/") or "/careers"
    host = parsed.netloc
    base_url = f"{parsed.scheme}://{host}{base_path}"
    return host, base_url


def _extract_eightfold_slug(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    match = re.search(r"/job/(\d+)-([^/?]+)", parsed.path)
    if not match:
        raise ValueError(f"Could not parse Eightfold job URL: {url}")
    return match.group(1), unquote(match.group(2)).strip("-")


def _humanize_slug_text(text: str) -> str:
    text = unquote(text)
    text = text.replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()
    pretty = text.title()
    replacements = {
        "Ai": "AI",
        "Ml": "ML",
        "Llms": "LLMs",
        "Llm": "LLM",
        "Ts": "TS",
        "Sci": "SCI",
        "Bi": "BI",
        "Qa": "QA",
        "Hr": "HR",
        "Ui": "UI",
        "Ux": "UX",
        "Aws": "AWS",
        "Gcp": "GCP",
        "Sql": "SQL",
        "Api": "API",
    }
    for src, dst in replacements.items():
        pretty = re.sub(rf"\b{src}\b", dst, pretty)
    return pretty


def _guess_eightfold_location(slug_text: str) -> str:
    slug_text = slug_text.lower().strip("-")
    if slug_text.endswith("remote-any-state-united-states-of-america"):
        return "Remote Any State, United States of America"
    if slug_text.endswith("nationwide-united-states-of-america"):
        return "Nationwide, United States of America"

    for country_slug, country_label in sorted(EIGHTFOLD_COUNTRY_SLUGS.items(), key=lambda item: len(item[0]), reverse=True):
        if not slug_text.endswith(country_slug):
            continue
        prefix = slug_text[: -len(country_slug)].rstrip("-")
        for region_slug, region_label in sorted(EIGHTFOLD_REGION_SLUGS.items(), key=lambda item: len(item[0]), reverse=True):
            if prefix.endswith(region_slug):
                return f"{region_label}, {country_label}"
        return country_label
    return ""


def _build_eightfold_stub(job_url: str, updated_at: str, source_slug: str) -> dict:
    job_id, slug_text = _extract_eightfold_slug(job_url)
    location_hint = _guess_eightfold_location(slug_text)
    return {
        "id": job_id,
        "title": _humanize_slug_text(slug_text),
        "location": location_hint,
        "url": job_url,
        "updated_at": updated_at,
        "departments": [],
        "content_html": "",
        "source_platform": "eightfold",
        "source_slug": source_slug,
        "search_text": slug_text.replace("-", " "),
        "location_search_text": location_hint.lower(),
    }


def _extract_jobposting_ld_json(soup: BeautifulSoup) -> dict:
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            payload = json.loads(script.string or script.get_text())
        except json.JSONDecodeError:
            continue
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and item.get("@type") == "JobPosting":
                    return item
        elif isinstance(payload, dict) and payload.get("@type") == "JobPosting":
            return payload
    raise ValueError("No JobPosting JSON-LD found on Eightfold job page")


def _description_text_to_html(description: str) -> str:
    chunks = [chunk.strip() for chunk in description.split("\n\n") if chunk.strip()]
    if not chunks:
        return html_mod.escape(description)
    return "".join(
        f"<p>{html_mod.escape(chunk).replace(chr(10), '<br/>')}</p>"
        for chunk in chunks
    )


def _extract_jobposting_location(jobposting: dict) -> str:
    raw_location = jobposting.get("jobLocation")
    if isinstance(raw_location, list):
        raw_location = raw_location[0] if raw_location else {}
    if not isinstance(raw_location, dict):
        return ""

    address = raw_location.get("address", {})
    locality = address.get("addressLocality", "")
    region = address.get("addressRegion", "")
    country = address.get("addressCountry", "")

    if isinstance(country, dict):
        country = country.get("name", "")
    if isinstance(region, dict):
        region = region.get("name", "")

    region = region.split(",")[0] if region else ""
    parts = [part for part in (locality, region, country) if part]
    return ", ".join(parts)


def _extract_description_field(description: str, field_name: str) -> str:
    pattern = rf"{re.escape(field_name)}:\s*(.+)"
    match = re.search(pattern, description, re.IGNORECASE)
    if not match:
        return ""
    return match.group(1).splitlines()[0].strip()


def fetch_eightfold_job_detail_from_url(job_url: str, updated_at: str = "", source_slug: str = "") -> dict:
    """Fetch a single Eightfold job page and parse JobPosting JSON-LD."""
    resp = _http_get(job_url)
    soup = BeautifulSoup(resp.text, "html.parser")
    jobposting = _extract_jobposting_ld_json(soup)

    title = jobposting.get("title") or (soup.title.get_text(strip=True).replace(" | CACI", "") if soup.title else "")
    description = html_mod.unescape(jobposting.get("description", ""))
    departments = []
    job_category = _extract_description_field(description, "Job Category")
    if job_category:
        departments.append(job_category)

    job_id, slug_text = _extract_eightfold_slug(job_url)
    location = _extract_jobposting_location(jobposting) or _guess_eightfold_location(slug_text)

    return {
        "id": job_id,
        "title": title or _humanize_slug_text(slug_text),
        "location": location,
        "url": jobposting.get("url") or job_url,
        "updated_at": updated_at or jobposting.get("datePosted", ""),
        "departments": departments,
        "content_html": _description_text_to_html(description),
        "source_platform": "eightfold",
        "source_slug": source_slug or urlparse(job_url).netloc,
        "search_text": slug_text.replace("-", " "),
        "location_search_text": location.lower(),
    }


def hydrate_eightfold_jobs(jobs: list[dict], max_workers: int = 12) -> list[dict]:
    """Fetch full details for a filtered subset of Eightfold jobs."""
    if not jobs:
        return []

    hydrated: list[dict | None] = [None] * len(jobs)
    workers = min(max_workers, len(jobs))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_index = {
            executor.submit(
                fetch_eightfold_job_detail_from_url,
                job["url"],
                job.get("updated_at", ""),
                job.get("source_slug", ""),
            ): index
            for index, job in enumerate(jobs)
        }
        for future in concurrent.futures.as_completed(future_to_index):
            index = future_to_index[future]
            try:
                hydrated[index] = future.result()
            except Exception as exc:
                print(f"Warning: failed to hydrate Eightfold job {jobs[index].get('url', '')}: {exc}", file=sys.stderr)
                hydrated[index] = jobs[index]

    return [job for job in hydrated if job]


def fetch_eightfold(slug: str, include_content: bool = False) -> list[dict]:
    """Fetch jobs from an Eightfold public careers site via its sitemap."""
    source_slug, base_url = _normalize_eightfold_base(slug)
    sitemap_url = f"{base_url}/sitemap.xml"
    resp = _http_get(sitemap_url)
    soup = BeautifulSoup(resp.text, "xml")

    jobs = []
    for url_tag in soup.find_all("url"):
        loc = url_tag.find("loc")
        if not loc or "/job/" not in loc.text:
            continue
        lastmod = url_tag.find("lastmod")
        jobs.append(_build_eightfold_stub(loc.text.strip(), lastmod.get_text(strip=True) if lastmod else "", source_slug))

    if include_content:
        return hydrate_eightfold_jobs(jobs)
    return jobs


def fetch_eightfold_job_detail(slug: str, job_id: str) -> dict:
    """Fetch full details for a single Eightfold job by looking it up in the sitemap."""
    jobs = fetch_eightfold(slug, include_content=False)
    for job in jobs:
        if job["id"] == str(job_id):
            return fetch_eightfold_job_detail_from_url(job["url"], job.get("updated_at", ""), job.get("source_slug", ""))
    raise ValueError(f"Could not find Eightfold job id {job_id} for {slug}")


PLATFORM_FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "eightfold": fetch_eightfold,
    "ashby": fetch_ashby,
    "talentbrew": fetch_talentbrew,
}


LA_METRO_LOCATIONS = [
    "los angeles", "east la", "el monte", "pasadena", "glendale", "burbank",
    "long beach", "torrance", "santa monica", "culver city", "inglewood",
    "costa mesa", "irvine", "anaheim", "orange county", "newport beach",
    "el segundo", "playa vista", "marina del rey", "venice", "westwood",
    "beverly hills", "hollywood", "downtown la", "dtla",
    "west covina", "covina", "azusa", "glendora", "pomona", "san dimas",
    "la verne", "claremont", "walnut", "diamond bar", "rowland heights",
    "hacienda heights", "city of industry",
    "redondo beach", "hawthorne", "fullerton",
]

REMOTE_OR_HYBRID_TERMS = [
    "remote",
    "remote friendly",
    "hybrid",
]

US_LOCATION_TERMS = [
    "united states",
    "usa",
    "us",
    "u s",
    "any state",
    "nationwide",
    "us based",
    "u s based",
    "united states only",
    "us only",
    "u s only",
]

FOREIGN_LOCATION_TERMS = [
    "brazil", "portugal", "germany", "france", "italy", "india", "canada",
    "australia", "united kingdom", "uk", "ireland", "spain", "poland",
    "netherlands", "sweden", "denmark", "norway", "finland", "belgium",
    "switzerland", "austria", "singapore", "japan", "mexico", "argentina",
    "colombia", "chile", "new zealand", "emea", "apac", "latam", "europe",
]


def normalize_location_text(text: str) -> str:
    """Normalize location text for heuristic matching."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _contains_any_location_term(text: str, terms: list[str]) -> bool:
    normalized = normalize_location_text(text)
    return any(re.search(rf"\b{re.escape(term)}\b", normalized) for term in terms)


def is_remote_or_hybrid_location(text: str) -> bool:
    """Return True when a location indicates remote or hybrid work."""
    return _contains_any_location_term(text, REMOTE_OR_HYBRID_TERMS)


def is_explicitly_foreign_location(text: str) -> bool:
    """Return True for non-US country or region restrictions."""
    if _contains_any_location_term(text, US_LOCATION_TERMS):
        return False
    return _contains_any_location_term(text, FOREIGN_LOCATION_TERMS)


def is_us_compatible_remote_or_hybrid(text: str) -> bool:
    """Allow remote or hybrid roles that are US-based or have no foreign restriction."""
    if not is_remote_or_hybrid_location(text):
        return False
    if is_explicitly_foreign_location(text):
        return False
    return True


def matches_la_or_remote_filter(text: str) -> bool:
    """LA metro, East LA, or viable remote/hybrid roles for the user."""
    normalized = normalize_location_text(text)
    return (
        any(alias in normalized for alias in LA_METRO_LOCATIONS)
        or is_us_compatible_remote_or_hybrid(normalized)
    )


def filter_jobs(
    jobs: list[dict],
    keywords: list[str] | None = None,
    location: str | None = None,
) -> list[dict]:
    """Filter jobs by keyword and location."""
    filtered = jobs

    if keywords:
        kw_patterns = [re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE) for kw in keywords]
        filtered = [
            j for j in filtered
            if any(
                p.search(j["title"]) or
                p.search(j.get("search_text", "")) or
                any(p.search(d) for d in j["departments"])
                for p in kw_patterns
            )
        ]

    if location:
        loc_lower = location.lower()
        if loc_lower in ["los angeles", "la", "east la", "la metro", "socal"]:
            filtered = [
                j for j in filtered
                if matches_la_or_remote_filter(f"{j['location']} {j.get('location_search_text', '')}")
            ]
        else:
            loc_pattern = re.compile(re.escape(location), re.IGNORECASE)
            filtered = [
                j for j in filtered
                if loc_pattern.search(j["location"]) or loc_pattern.search(j.get("location_search_text", ""))
            ]

    return filtered


def save_jobs_to_file(jobs: list[dict], slug: str) -> Path:
    """Save fetched jobs to a JSON file in data/job_postings/."""
    outdir = DATA_DIR / "job_postings"
    outdir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d")
    outfile = outdir / f"{slug}_{timestamp}_jobs.json"
    with open(outfile, "w") as f:
        json.dump({"fetched_at": datetime.now(timezone.utc).isoformat(), "slug": slug, "count": len(jobs), "jobs": jobs}, f, indent=2)
    return outfile


def print_jobs_table(jobs: list[dict], limit: int = 50):
    """Print jobs as a formatted table."""
    if not jobs:
        print("No jobs found matching criteria.")
        return

    print(f"\n{'#':<4} {'Title':<55} {'Location':<35} {'Department'}")
    print("-" * 130)
    for i, j in enumerate(jobs[:limit], 1):
        dept = ", ".join(d for d in j["departments"] if d)[:30]
        print(f"{i:<4} {j['title'][:54]:<55} {j['location'][:34]:<35} {dept}")

    if len(jobs) > limit:
        print(f"\n... and {len(jobs) - limit} more jobs (use --limit to show more)")
    print(f"\nTotal: {len(jobs)} jobs")


def main():
    parser = argparse.ArgumentParser(description="Fetch jobs from company career pages")
    parser.add_argument("slug", help="Company slug on the ATS platform")
    parser.add_argument("--platform", "-p", choices=["greenhouse", "lever", "eightfold", "ashby", "talentbrew"], default="greenhouse", help="ATS platform")
    parser.add_argument("--keywords", "-k", help="Comma-separated keywords to filter by (matches title and department)")
    parser.add_argument("--location", "-l", help="Location filter (e.g., 'los angeles', 'remote')")
    parser.add_argument("--save", "-s", action="store_true", help="Save results to data/job_postings/")
    parser.add_argument("--json", action="store_true", help="Output as JSON instead of table")
    parser.add_argument("--limit", type=int, default=50, help="Max jobs to display (default: 50)")
    parser.add_argument("--with-content", action="store_true", help="Fetch full job descriptions (slower)")
    args = parser.parse_args()

    fetcher = PLATFORM_FETCHERS[args.platform]
    print(f"Fetching jobs from {args.platform}/{args.slug}...", file=sys.stderr)

    try:
        if args.platform in {"greenhouse", "eightfold", "ashby", "talentbrew"}:
            jobs = fetcher(args.slug, include_content=args.with_content)
        else:
            jobs = fetcher(args.slug)
    except Exception as e:
        print(f"Error fetching jobs: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Fetched {len(jobs)} total jobs.", file=sys.stderr)

    keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else None
    filtered = filter_jobs(jobs, keywords=keywords, location=args.location)

    if keywords or args.location:
        print(f"After filtering: {len(filtered)} jobs.", file=sys.stderr)

    if args.save:
        outfile = save_jobs_to_file(filtered, args.slug)
        print(f"Saved to {outfile}", file=sys.stderr)

    if args.json:
        json.dump(filtered[:args.limit], sys.stdout, indent=2)
    else:
        print_jobs_table(filtered, limit=args.limit)


if __name__ == "__main__":
    main()
