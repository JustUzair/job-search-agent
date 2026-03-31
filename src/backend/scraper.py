import os
import re
import time
import hashlib
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

try:
    from . import db, llm
    from . import sources_ats
except ImportError:
    import db, llm
    import sources_ats

IST = timezone(timedelta(hours=5, minutes=30))
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; job-hunter-bot/1.0)"}


def _uid(*parts):
    return hashlib.md5("-".join(parts).encode()).hexdigest()[:16]


def _now_ist():
    return datetime.now(IST).isoformat()


def _first_word(text):
    return re.split(r"[\s(|]", text)[0][:60]


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


# ── Title pre-filter ──────────────────────────────────────────────────────────

def passes_title_filter(title: str, skip_patterns: list) -> bool:
    """Return False if the job title matches any skip pattern (case-insensitive).

    This runs before keyword matching and LLM scoring to cheaply drop roles
    like 'Marketing Manager' or 'Mechanical Engineer' found at tech companies.
    """
    t = title.lower()
    return not any(p.lower() in t for p in skip_patterns)


# ── Sources ───────────────────────────────────────────────────────────────────
def scrape_hn_jobs():
    """Scrape recent HN job posts via Algolia search_by_date API (last 30 days)."""
    jobs = []
    try:
        from datetime import datetime, timezone, timedelta
        cutoff = int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp())
        r = requests.get(
            "https://hn.algolia.com/api/v1/search_by_date",
            params={"tags": "job", "hitsPerPage": 100, "numericFilters": f"created_at_i>{cutoff}"},
            headers=HEADERS,
            timeout=10,
        )
        hits = r.json().get("hits", [])
        for hit in hits:
            title = hit.get("title") or hit.get("story_title") or ""
            if not title:
                continue
            # Use the external URL if available, otherwise the HN item URL
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            uid = _uid("hn", str(hit.get("objectID", title)))
            if db.job_exists(uid):
                continue
            posted_raw = hit.get("created_at") or ""
            posted_at = posted_raw[:10] if posted_raw else ""  # YYYY-MM-DD
            jobs.append(dict(
                id=uid, source="hn_jobs", title=title[:200],
                company=_first_word(title), url=url,
                description=title,
                work_type=detect_work_type(title), location=detect_location(title),
                posted_at=posted_at,
            ))
    except Exception as e:
        print(f"[hn_jobs] {e}")
    return jobs


def scrape_hn_jobs_page(max_pages=5):
    """Scrape news.ycombinator.com/jobs — plain HTML, no JS needed.

    Each job row: <tr class="athing submission"> with title in <span class="titleline"><a>,
    company domain in <span class="sitestr">, date in <span class="age" title="ISO...">.
    Pagination: <a class='morelink'> with href like 'jobs?next=...&n=31'.
    """
    jobs = []
    url = "https://news.ycombinator.com/jobs"
    try:
        for _ in range(max_pages):
            r = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            rows = soup.select("tr.athing.submission")
            if not rows:
                break

            for row in rows:
                item_id = row.get("id", "")
                title_el = row.select_one("span.titleline > a")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                if not href.startswith("http"):
                    href = f"https://news.ycombinator.com/{href}" if href else f"https://news.ycombinator.com/item?id={item_id}"

                site_el = row.select_one("span.sitestr")
                company = site_el.get_text(strip=True) if site_el else _first_word(title)

                # Date from the next sibling row's <span class="age">
                age_el = row.find_next("span", class_="age")
                posted_at = ""
                if age_el and age_el.get("title"):
                    posted_at = age_el["title"][:10]  # YYYY-MM-DD from ISO

                uid = _uid("hn-page", item_id or title)
                if db.job_exists(uid):
                    continue
                jobs.append(dict(
                    id=uid, source="hn_jobs_page", title=title[:200],
                    company=company[:80], url=href,
                    description=title,
                    work_type=detect_work_type(title), location=detect_location(title),
                    posted_at=posted_at,
                ))

            # Follow pagination
            more = soup.select_one("a.morelink")
            if not more:
                break
            next_href = more.get("href", "")
            url = f"https://news.ycombinator.com/{next_href}" if next_href else None
            if not url:
                break
    except Exception as e:
        print(f"[hn_jobs_page] {e}")
    return jobs


def _playwright_get_html(url, wait_ms=2500):
    """Render a URL with Playwright and return the HTML. Returns None on failure."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto(url, timeout=30000)
            page.wait_for_timeout(wait_ms)
            html = page.content()
            browser.close()
        return html
    except Exception as e:
        print(f"[playwright] {url}: {e}")
        return None


def scrape_web3career(max_pages=10):
    """Scrape web3.career/remote-jobs with pagination, 30-day cutoff.

    Uses Playwright (JS-rendered). Pages via ?page=N.
    Stops when jobs are older than 30 days.
    """
    jobs = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page_ctx = browser.new_page(user_agent=HEADERS["User-Agent"])
            stop_paging = False

            for page_num in range(1, max_pages + 1):
                url = f"https://web3.career/remote-jobs?page={page_num}"
                print(f"  web3career page {page_num}...")
                page_ctx.goto(url, timeout=30000)
                page_ctx.wait_for_timeout(3000)
                html = page_ctx.content()
                soup = BeautifulSoup(html, "html.parser")

                title_cells = soup.select("td[data-jobid][scope='row']")
                if not title_cells:
                    seen_ids = set()
                    title_cells = []
                    for td in soup.select("td[data-jobid]"):
                        jid = td.get("data-jobid")
                        if jid and jid not in seen_ids:
                            seen_ids.add(jid)
                            title_cells.append(td)

                if not title_cells:
                    break  # no more jobs

                page_jobs_before = len(jobs)
                for td in title_cells:
                    job_id = td.get("data-jobid", "")
                    a = td.select_one("a[href]")
                    if not a:
                        continue
                    title = a.get_text(strip=True)
                    if not title or len(title) < 5:
                        continue
                    href = a.get("href", "")
                    if not href.startswith("http"):
                        href = "https://web3.career" + href

                    siblings = soup.select(f"td[data-jobid='{job_id}']")
                    company, posted_at, location, tags = "", "", "", ""
                    for sib in siblings:
                        if sib == td:
                            continue
                        h3 = sib.select_one("h3")
                        if h3 and not company:
                            company = h3.get_text(strip=True)[:80]
                            continue
                        time_el = sib.select_one("time[datetime]")
                        if time_el and not posted_at:
                            posted_at = time_el.get("datetime", "")[:30]
                            continue
                        badges = sib.select("a[class*='badge'], span[class*='badge'], [class*='tag']")
                        if badges:
                            tags = " ".join(b.get_text(strip=True) for b in badges)
                            continue
                        txt = sib.get_text(strip=True)
                        if txt and not location and len(txt) < 60:
                            location = txt

                    # 30-day cutoff check
                    if posted_at:
                        try:
                            job_date = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
                            if job_date.tzinfo is None:
                                job_date = job_date.replace(tzinfo=timezone.utc)
                            if job_date < cutoff:
                                stop_paging = True
                                continue
                        except (ValueError, TypeError):
                            pass

                    if not company:
                        company = _first_word(title)

                    uid = _uid("w3c", href)
                    if db.job_exists(uid):
                        continue
                    jobs.append(dict(
                        id=uid, source="web3career", title=title[:200],
                        company=company, url=href,
                        description=f"{title} {tags}".strip(),
                        work_type="remote", location=location or "remote",
                        posted_at=posted_at,
                    ))

                if stop_paging or len(jobs) == page_jobs_before:
                    break  # no new jobs or hit 30-day cutoff

            browser.close()
    except Exception as e:
        print(f"[web3career] {e}")
    print(f"  web3career: {len(jobs)} jobs across pages")
    return jobs


def scrape_cryptorank_funding():
    """Scrape cryptorank.io/funding-rounds with Playwright, scrolling for more rows."""
    jobs = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto("https://cryptorank.io/funding-rounds", timeout=30000)
            page.wait_for_timeout(4000)
            # Scroll down 3 times to load more rows via infinite scroll
            for _ in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1500)
            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")

        # Cryptorank uses a table; columns are roughly:
        # 0: project name+link, 1: amount, 2: round type, 3: date, 4+: other
        SKIP_NAMES = {"project", "funds raised", "round type", "date", "sum", "total",
                      "featured", "name", "#"}
        rows = soup.select("table tbody tr") or soup.select("tr[class*='Row']")
        seen = set()

        for row in rows:
            cells = row.select("td")
            if len(cells) < 2:
                continue

            # Name + source link from first cell
            name_el = cells[0].select_one("a[href], span[title]")
            name = (name_el.get_text(strip=True) if name_el else cells[0].get_text(strip=True))
            name = re.sub(r'\s+', ' ', name).strip()[:80]

            if not name or len(name) < 2 or name.lower() in SKIP_NAMES:
                continue
            # Skip rows that are clearly UI/label text
            if any(kw in name.lower() for kw in ["featured", "funds raised", "round type"]):
                continue
            if name in seen:
                continue
            seen.add(name)

            # Source URL (link to cryptorank project page)
            source_href = ""
            if name_el and name_el.name == "a":
                source_href = name_el.get("href", "")
                if source_href and not source_href.startswith("http"):
                    source_href = "https://cryptorank.io" + source_href

            # Amount — look for a cell containing $ or M/B
            amount = "?"
            for cell in cells[1:4]:
                txt = cell.get_text(strip=True)
                if any(c in txt for c in ["$", "M", "B", "K"]) and any(c.isdigit() for c in txt):
                    amount = txt[:50]
                    break

            # Round type — usually a short label like "Seed", "Series A", etc.
            round_type = ""
            for cell in cells[1:5]:
                txt = cell.get_text(strip=True)
                if any(kw in txt.lower() for kw in
                       ["seed", "series", "pre-seed", "strategic", "private", "public", "ido", "ico", "grant"]):
                    round_type = txt[:50]
                    break

            # Date — look for a cell that looks like a date
            announced_at = ""
            for cell in cells[1:6]:
                txt = cell.get_text(strip=True)
                if re.search(r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{4})\b', txt, re.I):
                    announced_at = txt[:30]
                    break

            uid = _uid("cr", name)
            careers = _find_careers(name)
            time.sleep(0.3)

            db.save_funded_company(dict(
                id=uid, company=name,
                amount=amount, round_type=round_type,
                careers_url=careers,
                source_url=source_href,
                announced_at=announced_at,
                found_at=_now_ist(),
            ))
            if careers:
                jobs.append(dict(
                    id=_uid("cr-job", name), source="cryptorank_funding",
                    title=f"Hiring at {name} (recently funded)",
                    company=name, url=careers,
                    description=f"{name} raised {amount} ({round_type}). Careers: {careers}",
                    work_type="unspecified", location="",
                ))
        print(f"  cryptorank: {len(seen)} companies, {len(jobs)} with careers pages")
    except Exception as e:
        print(f"[cryptorank] {e}")
    return jobs


def scrape_dropstab():
    """Scrape dropstab.com/latest-fundraising-rounds — JS-rendered, uses Playwright."""
    jobs = []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[dropstab] playwright not installed, skipping")
        return jobs

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto("https://dropstab.com/latest-fundraising-rounds", timeout=30000)
            # Wait for content to load
            page.wait_for_timeout(3000)

            # Try to find funding round rows
            # dropstab renders a table/list of funding rounds
            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")

        # Try to find company/round entries — dropstab uses various selectors
        entries = (
            soup.select("tr[class*='row'], div[class*='round'], div[class*='funding']") or
            soup.select("tbody tr") or
            soup.select("[class*='TableRow'], [class*='table-row']")
        )

        for entry in entries[:50]:
            # Extract company name — look for the primary text element
            name_el = entry.select_one(
                "td:first-child, [class*='name'], [class*='project'], a[href*='/coins/']"
            )
            if not name_el:
                continue
            name = name_el.get_text(strip=True)[:80]
            if not name or len(name) < 2:
                continue

            # Extract amount and round type
            tds = entry.select("td")
            amount = tds[1].get_text(strip=True) if len(tds) > 1 else "?"
            round_type = tds[2].get_text(strip=True) if len(tds) > 2 else ""

            uid = _uid("ds", name)
            careers = _find_careers(name)
            time.sleep(0.3)

            db.save_funded_company(dict(
                id=uid, company=name,
                amount=amount[:50],
                round_type=round_type[:50],
                careers_url=careers, found_at=_now_ist(),
            ))
            if careers:
                jobs.append(dict(
                    id=_uid("ds-job", name), source="dropstab_funding",
                    title=f"Hiring at {name} (recently funded, dropstab)",
                    company=name, url=careers,
                    description=f"{name} raised {amount}. Careers: {careers}",
                    work_type="unspecified", location="",
                ))
    except Exception as e:
        print(f"[dropstab] {e}")
    return jobs


def _find_careers(company_name):
    """Try to find a careers/jobs page for the company via DuckDuckGo."""
    CAREERS_DOMAINS = ["lever.co", "greenhouse.io", "ashbyhq.com", "workable.com",
                       "jobs.ashbyhq", "boards.greenhouse", "apply.workable"]
    try:
        q = f'"{company_name}" jobs careers'
        r = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": q},
            headers={**HEADERS, "Accept-Language": "en-US,en;q=0.9"},
            timeout=10,
        )
        soup = BeautifulSoup(r.text, "html.parser")
        # DuckDuckGo HTML results: anchors with class result__a hold the actual href
        for a in soup.select("a.result__a"):
            href = a.get("href", "")
            # DDG wraps URLs, unwrap if needed
            if "uddg=" in href:
                import urllib.parse
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                href = parsed.get("uddg", [href])[0]
            lo = href.lower()
            if any(d in lo for d in CAREERS_DOMAINS):
                return href[:300]
            if any(kw in lo for kw in ["/careers", "/jobs", "career"]):
                # Make sure it's plausibly related to the company
                slug = re.sub(r'[^a-z0-9]', '', company_name.lower())[:12]
                if slug and slug in re.sub(r'[^a-z0-9]', '', lo):
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

    # YoE filter — parse stated requirement from job text and compare to config
    max_yoe = cfg.get("max_yoe")
    if max_yoe is not None:
        # Match patterns like "5+ years", "4-6 years", "minimum 7 years experience"
        yoe_match = re.search(
            r'(\d+)\s*(?:\+|to|-|–)?\s*\d*\s*years?\s*(?:of\s*)?(?:experience|exp\b)',
            text,
        )
        if yoe_match:
            required_min = int(yoe_match.group(1))
            if required_min > int(max_yoe):
                return False

    return True


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_job(job: dict) -> tuple[int, str]:
    """Synchronous single-job scoring fallback (used when batching unavailable)."""
    candidate_profile = db.get_profile()
    data = llm.chat_json(llm._build_score_prompt(job, candidate_profile), max_tokens=80)
    return int(data.get("score", 0)), str(data.get("reason", ""))[:120]


def _submit_batch_scoring(jobs: list, now: str) -> dict:
    """
    Submit jobs for batch scoring via Anthropic Message Batches API (50% off).
    Saves jobs with status='pending_score'. Returns scrape summary immediately.
    Scores arrive later via poll_pending_batches().
    """
    from datetime import datetime, timezone
    candidate_profile = db.get_profile()

    batch_id = llm.create_scoring_batch(jobs, candidate_profile)
    if not batch_id:
        return None  # provider doesn't support batching

    # Save all jobs as pending_score so they show up in DB
    for job in jobs:
        job.update(score=0, reason="pending batch scoring", found_at=now,
                   status="pending_score", batch_id=batch_id)
        db.save_job(job)

    # Track the batch
    internal_id = hashlib.md5(batch_id.encode()).hexdigest()[:16]
    db.save_batch({
        "id": internal_id,
        "provider": llm.PROVIDER,
        "batch_id": batch_id,
        "status": "in_progress",
        "total_requests": len(jobs),
        "completed": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    print(f"[scrape] submitted batch {batch_id} with {len(jobs)} jobs for async scoring")
    return {"batch_id": batch_id, "jobs_submitted": len(jobs)}


def poll_pending_batches() -> dict:
    """
    Check all in-progress batches. For completed ones, update job scores.
    Called by APScheduler every 5 min and by POST /api/batches/poll.
    Returns summary of what was processed.
    """
    pending = db.get_pending_batches()
    if not pending:
        return {"checked": 0, "completed": 0, "jobs_scored": 0}

    total_scored = 0
    completed_count = 0

    for batch in pending:
        result = llm.poll_batch(batch["batch_id"], provider=batch.get("provider"))
        if not result or result["status"] == "in_progress":
            continue

        # Batch is done — update all job scores
        cfg = db.get_config()
        threshold = cfg.get("score_threshold", 60)

        for r in result["results"]:
            status = "new" if r["score"] >= threshold else "filtered"
            db.update_job_score(r["custom_id"], r["score"], r["reason"], status)
            total_scored += 1

        db.mark_batch_done(batch["batch_id"], result["status"])
        completed_count += 1
        print(f"[batch] {batch['batch_id']}: scored {len(result['results'])} jobs")

    return {"checked": len(pending), "completed": completed_count, "jobs_scored": total_scored}


# ── Main ──────────────────────────────────────────────────────────────────────

def run_scrape(sources=None):
    db.init_db()
    cfg = db.get_config()
    active = sources or ["hn_jobs", "hn_jobs_page", "web3career", "cryptorank", "dropstab", "ats"]
    skip_titles = cfg.get("skip_title_patterns", [])
    raw = []

    if "hn_jobs" in active:
        j = scrape_hn_jobs(); print(f"  hn_jobs: {len(j)}"); raw += j
    if "hn_jobs_page" in active:
        j = scrape_hn_jobs_page(); print(f"  hn_jobs_page: {len(j)}"); raw += j
    if "web3career" in active:
        j = scrape_web3career(); print(f"  web3career: {len(j)}"); raw += j
    if "cryptorank" in active:
        j = scrape_cryptorank_funding(); print(f"  cryptorank: {len(j)}"); raw += j
    if "dropstab" in active:
        j = scrape_dropstab(); print(f"  dropstab: {len(j)}"); raw += j
    if "ats" in active:
        j = sources_ats.scrape_ats(); print(f"  ats: {len(j)}"); raw += j

    # 1. Title pre-filter — cheapest check, runs before everything else
    title_passed = [j for j in raw if passes_title_filter(j.get("title", ""), skip_titles)]
    title_dropped = len(raw) - len(title_passed)
    if title_dropped:
        print(f"[scrape] title filter dropped {title_dropped} non-relevant roles")

    # 2. Search-config filter (keywords, work type, location, YoE)
    filtered = [j for j in title_passed if passes_filters(j, cfg)]
    print(f"[scrape] {len(raw)} raw → {len(title_passed)} title-ok → {len(filtered)} pass filters, scoring...")

    # Skip jobs already in DB (no need to re-score)
    new_jobs = [j for j in filtered if not db.job_exists(j["id"])]
    print(f"[scrape] {len(new_jobs)} new jobs to score ({len(filtered) - len(new_jobs)} already in DB)")

    threshold = cfg.get("score_threshold", 60)
    now = _now_ist()

    # ── Save ALL new jobs immediately with status='unscored' ──────────────────
    # 'unscored' is the resume marker — on next run these get picked up again.
    for job in new_jobs:
        db.save_job({**job, "score": 0, "reason": "not yet scored",
                     "found_at": now, "status": "unscored"})

    # ── Also grab any jobs from previous runs that never got scored ───────────
    unscored_ids = db.get_unscored_job_ids()
    # Merge: new_jobs already in list, add previously-unscored ones from DB
    already_unscored = [j for j in filtered if j["id"] in unscored_ids
                        and j not in new_jobs]
    to_score_pool = new_jobs + already_unscored

    # ── Cap scoring per run (ollama is slow) ─────────────────────────────────
    MAX_SCORE_PER_RUN = int(os.environ.get("MAX_SCORE_PER_RUN", "200"))
    to_score = to_score_pool[:MAX_SCORE_PER_RUN]
    skipped = len(to_score_pool) - len(to_score)
    if skipped:
        print(f"[scrape] {skipped} jobs deferred to next run (cap={MAX_SCORE_PER_RUN})")

    surfaced = []
    batch_info = None

    if to_score:
        batch_info = _submit_batch_scoring(to_score, now)

        if not batch_info:
            # Provider returned None — no batch support, score synchronously
            for job in to_score:
                score, reason = score_job(job)
                status = "new" if score >= threshold else "filtered"
                db.update_job_score(job["id"], score, reason, status)
                if score >= threshold:
                    surfaced.append({**job, "score": score, "reason": reason})
        else:
            # Ollama batch is synchronous — it blocks until all workers finish,
            # so we can poll immediately and have real scores right away.
            # OpenAI / Anthropic batches are async — scores arrive later via scheduler.
            if llm.PROVIDER == "ollama":
                poll_pending_batches()
                # Re-read scored jobs from DB so surfaced reflects actual scores
                for job in to_score:
                    row = db.get_job(job["id"])
                    if row and row.get("score", 0) >= threshold:
                        surfaced.append(row)
            # For async providers, surfaced stays empty — the frontend will show
            # jobs once the scheduler polls and scores them.

    # ── Save rejected (failed filter) jobs ───────────────────────────────────
    for job in raw:
        if job not in filtered and not db.job_exists(job["id"]):
            reason = ("title filter (non-relevant role)"
                      if not passes_title_filter(job.get("title", ""), skip_titles)
                      else "filtered out (work type / location / keywords)")
            db.save_job({**job, "score": 0, "reason": reason,
                         "found_at": now, "status": "filtered"})

    surfaced.sort(key=lambda x: x.get("score", 0), reverse=True)
    result = {"total": len(raw), "filtered": len(filtered),
              "new": len(new_jobs), "unscored_resumed": len(already_unscored),
              "surfaced": surfaced, "threshold": threshold}
    if batch_info:
        result["batch"] = batch_info
    return result