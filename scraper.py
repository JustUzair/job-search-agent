import os
import re
import time
import hashlib
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

import db
import llm

IST = timezone(timedelta(hours=5, minutes=30))
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; job-hunter-bot/1.0)"}


def _uid(*parts):
    return hashlib.md5("-".join(parts).encode()).hexdigest()[:16]


def _now_ist():
    return datetime.now(IST).isoformat()


# ── Work-type detection ───────────────────────────────────────────────────────

def detect_work_type(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["hybrid"]):
        return "hybrid"
    if any(w in t for w in ["remote"]):
        return "remote"
    if any(w in t for w in ["onsite", "on-site", "in-office", "in office"]):
        return "onsite"
    return "unspecified"


def detect_location(text: str) -> str:
    """Best-effort single-line location extraction."""
    patterns = [
        r"\b(remote|worldwide|global)\b",
        r"\b([A-Z][a-z]+(?:,\s*[A-Z]{2})?)\b",   # City, ST
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(0)[:60]
    return ""


# ── Sources ───────────────────────────────────────────────────────────────────

def scrape_hn_jobs():
    jobs = []
    try:
        r = requests.get("https://news.ycombinator.com/jobs", headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        for row in soup.select("tr.athing"):
            a = row.select_one("td.title a")
            if not a:
                continue
            title = a.get_text(strip=True)
            url = a.get("href", "")
            uid = _uid("hn", row.get("id", title))
            if db.job_exists(uid):
                continue
            jobs.append(dict(id=uid, source="hn_jobs", title=title[:200],
                             company=_first_word(title), url=url, description=title,
                             work_type=detect_work_type(title), location=detect_location(title)))
    except Exception as e:
        print(f"[hn_jobs] {e}")
    return jobs


def scrape_hn_whoishiring():
    jobs = []
    try:
        search = requests.get(
            "https://hn.algolia.com/api/v1/search",
            params={"query": "who is hiring", "tags": "story,ask_hn", "hitsPerPage": 5},
            timeout=10,
        ).json()
        story = next(
            (h for h in search.get("hits", []) if "who is hiring" in h.get("title", "").lower()),
            None,
        )
        if not story:
            return []
        data = requests.get(
            f"https://hn.algolia.com/api/v1/items/{story['objectID']}", timeout=10
        ).json()
        for child in data.get("children", [])[:120]:
            text = child.get("text") or ""
            if len(text) < 80:
                continue
            plain = BeautifulSoup(text, "html.parser").get_text()
            uid = _uid("hn-hiring", str(child.get("id", "")))
            if db.job_exists(uid):
                continue
            first_line = plain[:160].split("\n")[0]
            company = first_line.split("|")[0].strip()[:80] if "|" in first_line else "Unknown"
            jobs.append(dict(
                id=uid, source="hn_whoishiring", title=first_line[:200],
                company=company, url=f"https://news.ycombinator.com/item?id={child.get('id')}",
                description=plain[:2000],
                work_type=detect_work_type(plain), location=detect_location(plain),
            ))
    except Exception as e:
        print(f"[hn_whoishiring] {e}")
    return jobs


def scrape_web3career():
    jobs = []
    try:
        r = requests.get("https://web3.career/remote-jobs", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        for row in soup.select("tr"):
            a = row.select_one("h2 a, h3 a")
            if not a:
                continue
            title = a.get_text(strip=True)
            href = a.get("href", "")
            if href and not href.startswith("http"):
                href = "https://web3.career" + href
            company_el = row.select_one(".company-name, td:nth-child(2) a, h3")
            company = company_el.get_text(strip=True)[:80] if company_el else _first_word(title)
            uid = _uid("w3c", href or title)
            if db.job_exists(uid):
                continue
            jobs.append(dict(id=uid, source="web3career", title=title[:200],
                             company=company, url=href, description=title,
                             work_type="remote", location="remote"))
    except Exception as e:
        print(f"[web3career] {e}")
    return jobs


def scrape_cryptorank_funding():
    jobs = []
    try:
        r = requests.get(
            "https://cryptorank.io/api/v0/funding-rounds",
            params={"limit": 50, "offset": 0},
            headers={**HEADERS, "Accept": "application/json"},
            timeout=15,
        )
        if r.status_code != 200:
            print(f"[cryptorank] HTTP {r.status_code}")
            return []
        for item in r.json().get("data", []):
            name = (item.get("project") or {}).get("name") or item.get("name", "")
            if not name:
                continue
            uid = _uid("cr", name)
            careers = _find_careers(name)
            time.sleep(0.4)
            db.save_funded_company(dict(
                id=uid, company=name,
                amount=str(item.get("amountInUSD") or item.get("amount") or "?"),
                round_type=str(item.get("roundType") or item.get("type") or ""),
                careers_url=careers, found_at=_now_ist(),
            ))
            if careers:
                jobs.append(dict(
                    id=_uid("cr-job", name), source="cryptorank_funding",
                    title=f"Hiring at {name} (recently funded)",
                    company=name, url=careers,
                    description=f"{name} raised funds. Careers: {careers}",
                    work_type="unspecified", location="",
                ))
    except Exception as e:
        print(f"[cryptorank] {e}")
    return jobs


def _find_careers(company_name):
    try:
        q = f"{company_name} crypto jobs site:lever.co OR site:greenhouse.io OR site:ashbyhq.com"
        r = requests.get("https://html.duckduckgo.com/html/",
                         params={"q": q}, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select("a.result__url, a.result__a"):
            href = a.get("href", "")
            if any(x in href for x in ["lever.co", "greenhouse.io", "ashbyhq", "careers", "/jobs"]):
                return href[:300]
    except Exception:
        pass
    return ""


# ── Filtering ─────────────────────────────────────────────────────────────────

def passes_filters(job: dict, cfg: dict) -> bool:
    """Return True if job passes the user's search config filters."""
    text = f"{job.get('title','')} {job.get('description','')}".lower()

    # Must match at least one keyword
    keywords = [k.lower() for k in cfg.get("keywords", [])]
    if keywords and not any(k in text for k in keywords):
        return False

    # Work type filter
    allowed_types = [t.lower() for t in cfg.get("work_type", [])]
    if allowed_types and "unspecified" not in allowed_types:
        job_wt = job.get("work_type", "unspecified").lower()
        if job_wt != "unspecified" and job_wt not in allowed_types:
            return False

    # Exclude locations
    exclude = [loc.lower() for loc in cfg.get("exclude_locations", [])]
    loc_text = f"{job.get('location','')} {job.get('description','')}".lower()
    if any(ex in loc_text for ex in exclude):
        return False

    return True


# ── Scoring ───────────────────────────────────────────────────────────────────

CANDIDATE_PROFILE = """
Suhel Kapadia — Full Stack Engineer, 2+ years, Gujarat India, open to remote only.

Skills: Solidity, ERC4337, Hardhat, Ethers.js, Wagmi, Viem, OpenZeppelin, RainbowKit,
Node.js, NestJS, Go, Python, TypeScript, PostgreSQL, MongoDB, Redis, RabbitMQ,
React, Next.js, TailwindCSS, LangChain, PGVector, Docker, Prometheus, Grafana, AWS.

Recent work: AI data pipeline (Go/Python/NestJS), ERC4337 accounts 60% gas reduction,
AI agent on 10k tweets/day, 10k-node Go monitoring service, Web3 Chrome wallet,
Coinbase swap widget.

Wants: Remote Web3 / backend / AI / fullstack roles.
Hard no: onsite roles, mobile-only, pure frontend, US/EU in-office.
"""


def score_job(job: dict) -> tuple[int, str]:
    data = llm.chat_json(f"""Score this job for the candidate (0-100).

CANDIDATE:
{CANDIDATE_PROFILE}

JOB:
Title: {job['title']}
Company: {job['company']}
Work type: {job.get('work_type','?')}
Location: {job.get('location','?')}
Description: {job['description'][:1200]}

Rules:
- Score 0 if the role requires physical presence (onsite/in-office) anywhere
- Score 0 if it requires 5+ years experience for a junior/mid candidate
- Score based on tech stack overlap, seniority match, remote availability

Reply ONLY valid JSON: {{"score": <int>, "reason": "<max 100 chars>"}}""",
        max_tokens=80,
    )
    return int(data.get("score", 0)), str(data.get("reason", ""))[:120]


# ── Main ──────────────────────────────────────────────────────────────────────

def run_scrape(sources=None):
    db.init_db()
    cfg = db.get_config()
    active = sources or ["hn_jobs", "hn_whoishiring", "web3career", "cryptorank"]
    raw = []

    if "hn_jobs" in active:
        j = scrape_hn_jobs(); print(f"  hn_jobs: {len(j)}"); raw += j
    if "hn_whoishiring" in active:
        j = scrape_hn_whoishiring(); print(f"  hn_whoishiring: {len(j)}"); raw += j
    if "web3career" in active:
        j = scrape_web3career(); print(f"  web3career: {len(j)}"); raw += j
    if "cryptorank" in active:
        j = scrape_cryptorank_funding(); print(f"  cryptorank: {len(j)}"); raw += j

    # Apply filters before scoring (saves API calls)
    filtered = [j for j in raw if passes_filters(j, cfg)]
    print(f"[scrape] {len(raw)} new jobs, {len(filtered)} pass filters, scoring...")

    threshold = cfg.get("score_threshold", 60)
    surfaced = []
    now = _now_ist()

    for job in filtered:
        score, reason = score_job(job)
        job.update(score=score, reason=reason, found_at=now, status="new")
        db.save_job(job)
        if score >= threshold:
            surfaced.append(job)

    # Save filtered-out jobs with score=0 so they appear in full list
    for job in raw:
        if job not in filtered:
            job.update(score=0, reason="filtered out (work type / location / keywords)",
                       found_at=now, status="filtered")
            db.save_job(job)

    surfaced.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {"total": len(raw), "filtered": len(filtered), "surfaced": surfaced, "threshold": threshold}


def _first_word(text):
    return re.split(r"[\s(|]", text)[0][:60]
