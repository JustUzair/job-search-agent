import os
import re
import json
import time
import hashlib
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from openai import OpenAI

import db

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
SCORE_THRESHOLD = int(os.environ.get("SCORE_THRESHOLD", "60"))

CANDIDATE_PROFILE = """
Suhel Kapadia — Full Stack Engineer, 2+ years experience, based in Gujarat India (open to remote)

Strong: Solidity, ERC4337, Hardhat, Ethers.js, Wagmi, Viem, OpenZeppelin, RainbowKit,
Node.js, NestJS, Go, Python, TypeScript, PostgreSQL, MongoDB, Redis, RabbitMQ,
React, Next.js, TailwindCSS, LangChain, PGVector, Docker, Prometheus, Grafana, AWS

Recent: AI data pipeline (Go/Python/NestJS/RabbitMQ), ERC4337 accounts (60% gas reduction),
AI agent on 10k+ tweets/day, 10k node monitoring in Go, Web3 Chrome wallet, Coinbase swap widget

Wants: Remote roles in Web3 / backend / AI pipelines / fullstack
Not interested in: pure frontend, mobile-only, non-technical
"""

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; job-hunter-bot/1.0)"}


def _uid(*parts: str) -> str:
    """Stable short ID from arbitrary strings."""
    raw = "-".join(parts)
    return hashlib.md5(raw.encode()).hexdigest()[:16]


# ── Sources ───────────────────────────────────────────────────────────────────

def scrape_hn_jobs() -> list[dict]:
    """news.ycombinator.com/jobs — paid YC startup postings."""
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
            jobs.append(dict(
                id=uid, source="hn_jobs", title=title[:200],
                company=_first_word(title), url=url, description=title,
            ))
    except Exception as e:
        print(f"[hn_jobs] {e}")
    return jobs


def scrape_hn_whoishiring() -> list[dict]:
    """HN Who Is Hiring thread via Algolia API — free, no scraping needed."""
    jobs = []
    try:
        search = requests.get(
            "https://hn.algolia.com/api/v1/search",
            params={"query": "who is hiring", "tags": "story,ask_hn", "hitsPerPage": 5},
            timeout=10,
        ).json()
        story = next(
            (h for h in search.get("hits", [])
             if "who is hiring" in h.get("title", "").lower()),
            None,
        )
        if not story:
            return []

        data = requests.get(
            f"https://hn.algolia.com/api/v1/items/{story['objectID']}",
            timeout=10,
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
            ))
    except Exception as e:
        print(f"[hn_whoishiring] {e}")
    return jobs


def scrape_web3career() -> list[dict]:
    """web3.career/remote-jobs — server-rendered, simple scrape."""
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
            jobs.append(dict(
                id=uid, source="web3career", title=title[:200],
                company=company, url=href, description=title,
            ))
    except Exception as e:
        print(f"[web3career] {e}")
    return jobs


def scrape_cryptorank_funding() -> list[dict]:
    """
    Cryptorank funding rounds via their internal API.
    Returns a list of recently funded companies (saved separately in DB).
    Also emits them as jobs so they appear in the digest.
    """
    companies = []
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

            # Find careers page (quick DuckDuckGo search)
            careers = _find_careers(name)
            time.sleep(0.4)

            company = dict(
                id=uid, company=name,
                amount=str(item.get("amountInUSD") or item.get("amount") or "?"),
                round_type=str(item.get("roundType") or item.get("type") or ""),
                careers_url=careers,
                found_at=datetime.now().isoformat(),
            )
            db.save_funded_company(company)

            if careers:
                companies.append(dict(
                    id=_uid("cr-job", name),
                    source="cryptorank_funding",
                    title=f"Hiring at {name} (recently funded)",
                    company=name,
                    url=careers,
                    description=f"{name} raised {company['amount']} ({company['round_type']}). Careers: {careers}",
                ))
    except Exception as e:
        print(f"[cryptorank] {e}")
    return companies


def _find_careers(company_name: str) -> str:
    """DuckDuckGo search for a company's careers page on known ATS platforms."""
    try:
        q = f"{company_name} crypto jobs site:lever.co OR site:greenhouse.io OR site:ashbyhq.com OR site:jobs.ashbyhq.com"
        r = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": q},
            headers=HEADERS,
            timeout=8,
        )
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select("a.result__url, a.result__a"):
            href = a.get("href", "")
            if any(x in href for x in ["lever.co", "greenhouse.io", "ashbyhq", "careers", "/jobs"]):
                return href[:300]
    except Exception:
        pass
    return ""


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_jobs(jobs: list[dict]) -> list[dict]:
    if not jobs or not OPENAI_API_KEY:
        return jobs

    client = OpenAI(api_key=OPENAI_API_KEY)
    scored = []

    for job in jobs:
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.1,
                max_tokens=80,
                messages=[{"role": "user", "content": f"""Score this job for the candidate (0-100).

CANDIDATE:
{CANDIDATE_PROFILE}

JOB:
Title: {job['title']}
Company: {job['company']}
Description: {job['description'][:1200]}

Reply ONLY with JSON (no markdown): {{"score": <int>, "reason": "<max 100 chars>"}}"""}],
            )
            raw = resp.choices[0].message.content.strip().strip("`").strip()
            raw = re.sub(r"^json", "", raw).strip()
            data = json.loads(raw)
            job["score"] = int(data.get("score", 0))
            job["reason"] = str(data.get("reason", ""))[:120]
        except Exception as e:
            print(f"  [score] {job['title'][:40]} — {e}")
            job["score"] = 0
            job["reason"] = "scoring failed"
        scored.append(job)

    return scored


# ── Main entry point ──────────────────────────────────────────────────────────

def run_scrape(sources: list[str] | None = None) -> dict:
    """
    Scrape all (or specific) sources, score new jobs, save to DB.
    Returns a result dict with surfaced jobs above threshold.
    """
    db.init_db()
    active = sources or ["hn_jobs", "hn_whoishiring", "web3career", "cryptorank"]
    raw_jobs = []

    print(f"[scrape] Starting — sources: {active}")

    if "hn_jobs" in active:
        j = scrape_hn_jobs()
        print(f"  hn_jobs: {len(j)} new")
        raw_jobs += j

    if "hn_whoishiring" in active:
        j = scrape_hn_whoishiring()
        print(f"  hn_whoishiring: {len(j)} new")
        raw_jobs += j

    if "web3career" in active:
        j = scrape_web3career()
        print(f"  web3career: {len(j)} new")
        raw_jobs += j

    if "cryptorank" in active:
        j = scrape_cryptorank_funding()
        print(f"  cryptorank: {len(j)} new funded companies with careers")
        raw_jobs += j

    print(f"[scrape] Scoring {len(raw_jobs)} new jobs...")
    scored = score_jobs(raw_jobs)

    now = datetime.now().isoformat()
    surfaced = []
    for job in scored:
        job["found_at"] = now
        job["status"] = "new"
        db.save_job(job)
        if job.get("score", 0) >= SCORE_THRESHOLD:
            surfaced.append(job)

    surfaced.sort(key=lambda x: x.get("score", 0), reverse=True)
    print(f"[scrape] Done — {len(surfaced)} jobs above threshold {SCORE_THRESHOLD}")

    return {
        "total": len(scored),
        "surfaced": surfaced,
        "threshold": SCORE_THRESHOLD,
    }


def _first_word(text: str) -> str:
    return re.split(r"[\s(|]", text)[0][:60]
