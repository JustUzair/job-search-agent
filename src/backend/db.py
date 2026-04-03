import sqlite3
import os
import json

DB_PATH = os.environ.get("DB_PATH", "/app/data/jobs.db")

DEFAULT_CONFIG = {
    "keywords": [
        "rust", "axum", "rocket", "ai", "rag", "langchain", "langgraph", 
        "next.js", "typescript", "fullstack", "backend", "solana", 
        "smart contract", "web3 security"
    ],
    "work_type": ["remote"],
    "min_yoe": 0,
    "max_yoe": 5,
    "exclude_locations": ["onsite US", "onsite UK", "onsite Europe", "in-office", "hybrid"],
    "score_threshold": 60,
    # Title substrings to instantly disqualify
    # DuckDuckGo site: search queries — used for autonomous ATS scraping.
    # Format: "<keywords> site:<ats-domain>"  (no https://)
    # Each keyword in config.keywords gets combined with each site to form a search.
    "site_search_queries": [
        'fullstack remote site:jobs.ashbyhq.com',
        'backend remote site:jobs.workable.com',
        'fullstack remote site:job-boards.greenhouse.io',
        'backend remote site:jobs.lever.co',
    ],
        "skip_title_patterns": [
        "marketing manager", "content writer", "content strategist", "seo specialist",
        "social media manager", "social media specialist", "brand manager",
        "communications manager", "pr manager", "public relations", "copywriter",
        "graphic designer", "motion designer", "video editor", "illustrator",
        "recruiter", "talent acquisition", "hr manager", "hr generalist",
        "human resources manager", "people operations manager",
        "accountant", "staff accountant", "financial analyst", "controller",
        "accounts receivable", "accounts payable", "bookkeeper",
        "legal counsel", "paralegal", "compliance analyst", "compliance officer",
        "mechanical engineer", "electrical engineer", "hardware engineer",
        "firmware engineer", "manufacturing engineer", "supply chain",
        "customer support", "customer success manager", "customer success",
        "account executive", "sales representative", "sales development representative",
        "sales director", "sales manager", "sales engineer",
        "business development representative", "business development manager",
        "office manager", "executive assistant", "administrative assistant",
        "receptionist", "data entry", "payroll",
    ],
}


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _migrate(conn):
    """Add missing columns to existing tables without destroying data."""
    existing_jobs = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
    job_migrations = [
        ("work_type",  "TEXT DEFAULT ''"),
        ("location",   "TEXT DEFAULT ''"),
        ("posted_at",  "TEXT DEFAULT ''"),
    ]
    for col, typedef in job_migrations:
        if col not in existing_jobs:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {typedef}")

    existing_funded = {row[1] for row in conn.execute("PRAGMA table_info(funded_companies)")}
    funded_migrations = [
        ("source_url",    "TEXT DEFAULT ''"),
        ("announced_at",  "TEXT DEFAULT ''"),
    ]
    for col, typedef in funded_migrations:
        if col not in existing_funded:
            conn.execute(f"ALTER TABLE funded_companies ADD COLUMN {col} {typedef}")

    # Create ats_companies if it doesn't exist yet (can't ALTER into existence)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ats_companies (
            id            TEXT PRIMARY KEY,
            platform      TEXT NOT NULL,
            slug          TEXT NOT NULL,
            company_name  TEXT DEFAULT '',
            discovered_via TEXT DEFAULT '',
            last_fetched  TEXT DEFAULT '',
            active        INTEGER DEFAULT 1
        )
    """)

    # LLM batch tracking for async scoring (Anthropic Message Batches)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS llm_batches (
            id            TEXT PRIMARY KEY,
            provider      TEXT NOT NULL,
            batch_id      TEXT NOT NULL,
            status        TEXT DEFAULT 'in_progress',
            total_requests INTEGER DEFAULT 0,
            completed     INTEGER DEFAULT 0,
            created_at    TEXT,
            completed_at  TEXT DEFAULT ''
        )
    """)

    # Add batch_id to jobs so we know which batch scored them
    if "batch_id" not in existing_jobs:
        conn.execute("ALTER TABLE jobs ADD COLUMN batch_id TEXT DEFAULT ''")

    conn.commit()


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id          TEXT PRIMARY KEY,
            source      TEXT,
            title       TEXT,
            company     TEXT,
            url         TEXT,
            description TEXT,
            score       INTEGER DEFAULT 0,
            reason      TEXT,
            status      TEXT DEFAULT 'new',
            work_type   TEXT DEFAULT '',
            location    TEXT DEFAULT '',
            found_at    TEXT
        );
        CREATE TABLE IF NOT EXISTS funded_companies (
            id          TEXT PRIMARY KEY,
            company     TEXT,
            amount      TEXT,
            round_type  TEXT,
            careers_url TEXT DEFAULT '',
            found_at    TEXT
        );
        CREATE TABLE IF NOT EXISTS config (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS journal (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            entry      TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS resume_variants (
            id            TEXT PRIMARY KEY,
            job_id        TEXT,
            company       TEXT,
            title         TEXT,
            variant_name  TEXT,
            out_dir       TEXT,
            zip_path      TEXT,
            pdf_path      TEXT DEFAULT '',
            changed_files TEXT DEFAULT '[]',
            job_score     INTEGER DEFAULT 0,
            created_at    TEXT
        );
    """)
    _migrate(conn)  # safe to run every startup
    existing = conn.execute("SELECT key FROM config WHERE key = 'search'").fetchone()
    if not existing:
        conn.execute("INSERT INTO config (key, value) VALUES ('search', ?)",
                     (json.dumps(DEFAULT_CONFIG),))
        conn.commit()
    # Seed default profile if not yet stored
    existing_profile = conn.execute("SELECT key FROM config WHERE key = 'profile'").fetchone()
    if not existing_profile:
        conn.execute("INSERT INTO config (key, value) VALUES ('profile', ?)", (DEFAULT_PROFILE,))
        conn.commit()
    conn.close()


def job_exists(job_id):
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    return row is not None


def save_job(job):
    conn = get_conn()
    conn.execute("""
        INSERT OR IGNORE INTO jobs
        (id, source, title, company, url, description, score, reason,
         status, work_type, location, posted_at, found_at, batch_id)
        VALUES (:id, :source, :title, :company, :url, :description,
                :score, :reason, :status, :work_type, :location, :posted_at, :found_at, :batch_id)
    """, {
        **job,
        "work_type": job.get("work_type", ""),
        "location": job.get("location", ""),
        "posted_at": job.get("posted_at", ""),
        "batch_id": job.get("batch_id", ""),
    })
    conn.commit()
    conn.close()


def job_exists(job_id: str) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    return row is not None


def list_jobs(status="new", limit=50, offset=0):
    conn = get_conn()
    # Support comma-separated statuses e.g. "new,unscored"
    statuses = [s.strip() for s in status.split(",") if s.strip()]
    placeholders = ",".join("?" * len(statuses))
    rows = conn.execute(f"""
        SELECT id, title, company, url, score, reason, source, work_type, location, found_at, status
        FROM jobs WHERE status IN ({placeholders})
        ORDER BY score DESC, found_at DESC
        LIMIT ? OFFSET ?
    """, (*statuses, limit, offset)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_all_jobs(limit=200, offset=0, source=None, status=None):
    conn = get_conn()
    conditions = []
    params = []
    if source:
        conditions.append("source = ?")
        params.append(source)
    if status:
        conditions.append("status = ?")
        params.append(status)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params += [limit, offset]
    rows = conn.execute(f"""
        SELECT id, title, company, url, score, reason, source, work_type, location, status, found_at
        FROM jobs {where} ORDER BY score DESC LIMIT ? OFFSET ?
    """, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_jobs(status="new"):
    conn = get_conn()
    statuses = [s.strip() for s in status.split(",") if s.strip()]
    placeholders = ",".join("?" * len(statuses))
    n = conn.execute(
        f"SELECT COUNT(*) FROM jobs WHERE status IN ({placeholders})", statuses
    ).fetchone()[0]
    conn.close()
    return n


def count_all_jobs(source=None, status=None):
    conn = get_conn()
    conditions = []
    params = []
    if source:
        conditions.append("source = ?")
        params.append(source)
    if status:
        conditions.append("status = ?")
        params.append(status)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    n = conn.execute(f"SELECT COUNT(*) FROM jobs {where}", params).fetchone()[0]
    conn.close()
    return n


def get_job(job_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def set_status(job_id, status):
    conn = get_conn()
    conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
    conn.commit()
    conn.close()


def save_funded_company(company):
    conn = get_conn()
    conn.execute("""
        INSERT OR IGNORE INTO funded_companies
        (id, company, amount, round_type, careers_url, source_url, announced_at, found_at)
        VALUES (:id, :company, :amount, :round_type, :careers_url, :source_url, :announced_at, :found_at)
    """, {
        "id": company.get("id", ""),
        "company": company.get("company", ""),
        "amount": company.get("amount", ""),
        "round_type": company.get("round_type", ""),
        "careers_url": company.get("careers_url", ""),
        "source_url": company.get("source_url", ""),
        "announced_at": company.get("announced_at", ""),
        "found_at": company.get("found_at", ""),
    })
    conn.commit()
    conn.close()


def list_funded(limit=50):
    conn = get_conn()
    rows = conn.execute("""
        SELECT id, company, amount, round_type, careers_url, source_url, announced_at, found_at
        FROM funded_companies
        WHERE company != '' AND company NOT LIKE 'Sum:%'
        ORDER BY found_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_config():
    conn = get_conn()
    row = conn.execute("SELECT value FROM config WHERE key = 'search'").fetchone()
    conn.close()
    if not row:
        return dict(DEFAULT_CONFIG)
    cfg = json.loads(row[0])
    # Merge any new default keys not yet in the stored config
    for k, v in DEFAULT_CONFIG.items():
        if k not in cfg:
            cfg[k] = v
    return cfg


def set_config(cfg):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('search', ?)",
                 (json.dumps(cfg),))
    conn.commit()
    conn.close()


DEFAULT_PROFILE = """Uzair Saiyed — Full Stack & AI Engineer, 2x Global Hackathon Winner, Gujarat India, open to remote only.

Skills: Node.js, Next.js, TypeScript, Tailwind, RAG, LangGraph, 
LangChain, Vector Databases, Solidity, Rust (Axum), Solana, MongoDB, PostgreSQL, Docker, Vercel.

Recent work: Built a local AI Smart Contract Auditor with cloud LLM integration, 
Deployed "Tessera" (RAG AI agent), Developed real-time Rust Rocket chat room, 
Solutions Engineering & DevRel for Web3 dev tools.

Wants: Remote AI Engineering / Rust / Backend / Fullstack roles.
Hard no: Onsite roles, Hybrid roles, pure frontend, mobile-only."""


def get_profile() -> str:
    conn = get_conn()
    row = conn.execute("SELECT value FROM config WHERE key = 'profile'").fetchone()
    conn.close()
    return row[0] if row else DEFAULT_PROFILE


def set_profile(text: str):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('profile', ?)", (text,))
    conn.commit()
    conn.close()


def add_journal_entry(text, created_at):
    conn = get_conn()
    conn.execute("INSERT INTO journal (entry, created_at) VALUES (?, ?)", (text, created_at))
    conn.commit()
    conn.close()


def get_journal_entries(limit=30, offset=0):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, entry, created_at FROM journal ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_journal_entries():
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM journal").fetchone()[0]
    conn.close()
    return n


def save_variant(variant: dict):
    conn = get_conn()
    conn.execute("""
        INSERT OR IGNORE INTO resume_variants
        (id, job_id, company, title, variant_name, out_dir, zip_path,
         pdf_path, changed_files, job_score, created_at)
        VALUES (:id, :job_id, :company, :title, :variant_name, :out_dir, :zip_path,
                :pdf_path, :changed_files, :job_score, :created_at)
    """, {
        "id": variant.get("id", ""),
        "job_id": variant.get("job_id", ""),
        "company": variant.get("company", ""),
        "title": variant.get("title", ""),
        "variant_name": variant.get("variant_name", ""),
        "out_dir": variant.get("out_dir", ""),
        "zip_path": variant.get("zip_path", ""),
        "pdf_path": variant.get("pdf_path", ""),
        "changed_files": json.dumps(variant.get("changed_files", [])),
        "job_score": variant.get("job_score", 0),
        "created_at": variant.get("created_at", ""),
    })
    conn.commit()
    conn.close()


def list_variants(limit=50):
    conn = get_conn()
    rows = conn.execute("""
        SELECT id, job_id, company, title, variant_name, out_dir, zip_path,
               pdf_path, changed_files, job_score, created_at
        FROM resume_variants ORDER BY created_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    result = []
    for r in rows:
        row = dict(r)
        try:
            row["changed_files"] = json.loads(row["changed_files"])
        except Exception:
            row["changed_files"] = []
        result.append(row)
    return result


def get_variant(variant_id: str):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM resume_variants WHERE id = ?", (variant_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    result = dict(row)
    try:
        result["changed_files"] = json.loads(result["changed_files"])
    except Exception:
        result["changed_files"] = []
    return result


def backup_to_bytes() -> bytes:
    """Return the raw SQLite DB file as bytes for sending via Telegram."""
    conn = get_conn()
    import io
    buf = io.BytesIO()
    for chunk in conn.iterdump():
        pass  # iterdump is text; use backup API instead
    conn.close()

    with open(DB_PATH, "rb") as f:
        return f.read()


# ── ATS company registry ──────────────────────────────────────────────────────

def save_ats_company(c: dict):
    """Insert an ATS company (slug + platform). Ignores duplicates."""
    conn = get_conn()
    conn.execute("""
        INSERT OR IGNORE INTO ats_companies
            (id, platform, slug, company_name, discovered_via, last_fetched, active)
        VALUES (:id, :platform, :slug, :company_name, :discovered_via, :last_fetched, :active)
    """, {
        "id": c["id"],
        "platform": c["platform"],
        "slug": c["slug"],
        "company_name": c.get("company_name", ""),
        "discovered_via": c.get("discovered_via", ""),
        "last_fetched": c.get("last_fetched", ""),
        "active": c.get("active", 1),
    })
    conn.commit()
    conn.close()


def list_ats_companies(active_only: bool = True, stale_hours: int = 23) -> list:
    """Return ATS companies that are active and haven't been fetched recently."""
    conn = get_conn()
    if active_only:
        rows = conn.execute("""
            SELECT id, platform, slug, company_name, discovered_via, last_fetched
            FROM ats_companies
            WHERE active = 1
              AND (last_fetched = '' OR last_fetched IS NULL
                   OR datetime(last_fetched) < datetime('now', ? || ' hours'))
            ORDER BY last_fetched ASC
        """, (f"-{stale_hours}",)).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, platform, slug, company_name, discovered_via, last_fetched FROM ats_companies"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_ats_fetched(company_id: str, timestamp: str):
    """Record when a company's jobs were last fetched."""
    conn = get_conn()
    conn.execute(
        "UPDATE ats_companies SET last_fetched = ? WHERE id = ?",
        (timestamp, company_id),
    )
    conn.commit()
    conn.close()


def count_ats_companies() -> int:
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM ats_companies WHERE active = 1").fetchone()[0]
    conn.close()
    return n


def ats_company_exists(company_id: str) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM ats_companies WHERE id = ?", (company_id,)).fetchone()
    conn.close()
    return row is not None


# ── LLM Batch tracking ──────────────────────────────────────────────────────

def save_batch(batch: dict):
    conn = get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO llm_batches
           (id, provider, batch_id, status, total_requests, completed, created_at)
           VALUES (:id, :provider, :batch_id, :status, :total_requests, :completed, :created_at)""",
        batch,
    )
    conn.commit()
    conn.close()


def get_pending_batches() -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM llm_batches WHERE status = 'in_progress' ORDER BY created_at"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_batch_done(batch_id: str, status: str = "completed"):
    from datetime import datetime, timezone
    conn = get_conn()
    conn.execute(
        "UPDATE llm_batches SET status = ?, completed_at = ? WHERE batch_id = ?",
        (status, datetime.now(timezone.utc).isoformat(), batch_id),
    )
    conn.commit()
    conn.close()


def get_jobs_by_batch(batch_id: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM jobs WHERE batch_id = ?", (batch_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_distinct_sources() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT DISTINCT source FROM jobs ORDER BY source").fetchall()
    conn.close()
    return [r[0] for r in rows if r[0]]


def update_job_score(job_id: str, score: int, reason: str, status: str = "new"):
    conn = get_conn()
    conn.execute(
        "UPDATE jobs SET score = ?, reason = ?, status = ? WHERE id = ?",
        (score, reason, status, job_id),
    )
    conn.commit()
    conn.close()

def get_unscored_job_ids() -> set:
    """Return IDs of jobs saved but not yet scored (status='unscored')."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id FROM jobs WHERE status = 'unscored'"
    ).fetchall()
    conn.close()
    return {row[0] for row in rows}

# ── DDG site-search scrape log ────────────────────────────────────────────────

def _ensure_ddg_search_log(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ddg_search_log (
            id          TEXT PRIMARY KEY,
            query       TEXT NOT NULL,
            results_count INTEGER DEFAULT 0,
            searched_at TEXT
        )
    """)
    conn.commit()


def ddg_search_done_today(query: str) -> bool:
    """
    Return True only if this query was already searched today AND returned
    at least 1 result.

    A zero-result entry means the search failed (network block, timeout, etc.)
    and must be retried — we never consider a failed search as "done".
    """
    import hashlib
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    today = datetime.now(IST).date().isoformat()
    qid = hashlib.md5(query.encode()).hexdigest()[:16]
    conn = get_conn()
    _ensure_ddg_search_log(conn)
    row = conn.execute(
        "SELECT searched_at, results_count FROM ddg_search_log WHERE id = ?",
        (qid,),
    ).fetchone()
    conn.close()
    if not row:
        return False
    # Only skip if: searched today AND found real results
    searched_today = str(row["searched_at"] or "")[:10] == today
    had_results = (row["results_count"] or 0) > 0
    return searched_today and had_results


def log_ddg_search(query: str, results_count: int):
    """Record that a DDG search query was executed now."""
    import hashlib
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    qid = hashlib.md5(query.encode()).hexdigest()[:16]
    now = datetime.now(IST).isoformat()
    conn = get_conn()
    _ensure_ddg_search_log(conn)
    conn.execute(
        "INSERT OR REPLACE INTO ddg_search_log (id, query, results_count, searched_at) VALUES (?,?,?,?)",
        (qid, query, results_count, now),
    )
    conn.commit()
    conn.close()


def get_ddg_search_log(limit: int = 100) -> list:
    """Return recent DDG search log entries for the UI."""
    conn = get_conn()
    _ensure_ddg_search_log(conn)
    rows = conn.execute(
        "SELECT query, results_count, searched_at FROM ddg_search_log ORDER BY searched_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_unscored_jobs() -> list:
    """Return full job rows for all jobs with status='unscored'."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM jobs WHERE status = 'unscored' ORDER BY found_at ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def _ddg_search(query: str, max_results: int = 30) -> list:
    """
    Query DuckDuckGo and return a list of result URLs.

    Strategy:
      1. Try the `duckduckgo-search` (DDGS) library — uses a different endpoint
         that is not blocked by Docker/datacenter IP ranges.
      2. Fall back to raw HTML scrape of html.duckduckgo.com if DDGS fails.
         (This path is the one that times out from Docker — kept as last resort.)

    The raw HTML endpoint produces ConnectTimeoutError inside Docker because
    DuckDuckGo blocks datacenter IPs at the TCP level.  This is NOT an HTTP
    rate-limit (429) — there is no Retry-After header.  Switching to DDGS
    fixes it for most deployments; the fallback handles edge cases.
    """
    # ── Attempt 1: duckduckgo-search library ─────────────────────────────────
    try:
        from duckduckgo_search import DDGS
        with DDGS(timeout=15) as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        urls = [r["href"] for r in results if r.get("href", "").startswith("http")]
        if urls:
            return urls
    except Exception as e:
        print(f"[ddg_search] DDGS library error (falling back to raw HTML): {e}")

    # ── Attempt 2: raw HTML fallback ─────────────────────────────────────────
    for attempt in range(2):
        try:
            r = requests.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={**HEADERS, "Accept-Language": "en-US,en;q=0.9"},
                timeout=10,
            )
            soup = BeautifulSoup(r.text, "html.parser")
            urls = []
            for a in soup.select("a.result__a"):
                href = a.get("href", "")
                if "uddg=" in href:
                    import urllib.parse
                    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                    href = parsed.get("uddg", [href])[0]
                if href.startswith("http") and href not in urls:
                    urls.append(href)
                if len(urls) >= max_results:
                    break
            return urls
        except Exception as e:
            if attempt == 0:
                time.sleep(3)   # brief back-off before retry
            else:
                print(f"[ddg_search] query={query!r} error: {e}")
    return []