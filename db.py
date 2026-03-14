import sqlite3
import os
import json

DB_PATH = os.environ.get("DB_PATH", "/app/data/jobs.db")

DEFAULT_CONFIG = {
    "keywords": ["web3", "blockchain", "solidity", "fullstack", "backend", "node.js", "go", "python", "AI", "LLM"],
    "work_type": ["remote"],
    "min_yoe": 0,
    "max_yoe": 5,
    "exclude_locations": ["onsite US", "onsite UK", "onsite Europe", "in-office"],
    "score_threshold": 60,
}


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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
    """)
    conn.commit()
    existing = conn.execute("SELECT key FROM config WHERE key = 'search'").fetchone()
    if not existing:
        conn.execute("INSERT INTO config (key, value) VALUES ('search', ?)",
                     (json.dumps(DEFAULT_CONFIG),))
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
         status, work_type, location, found_at)
        VALUES (:id, :source, :title, :company, :url, :description,
                :score, :reason, :status, :work_type, :location, :found_at)
    """, {**job, "work_type": job.get("work_type", ""), "location": job.get("location", "")})
    conn.commit()
    conn.close()


def list_jobs(status="new", limit=50, offset=0):
    conn = get_conn()
    rows = conn.execute("""
        SELECT id, title, company, url, score, reason, source, work_type, location, found_at
        FROM jobs WHERE status = ? ORDER BY score DESC LIMIT ? OFFSET ?
    """, (status, limit, offset)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_all_jobs(limit=200, offset=0):
    conn = get_conn()
    rows = conn.execute("""
        SELECT id, title, company, url, score, reason, source, work_type, location, status, found_at
        FROM jobs ORDER BY score DESC LIMIT ? OFFSET ?
    """, (limit, offset)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_jobs(status=None):
    conn = get_conn()
    if status:
        n = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = ?", (status,)).fetchone()[0]
    else:
        n = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
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
        (id, company, amount, round_type, careers_url, found_at)
        VALUES (:id, :company, :amount, :round_type, :careers_url, :found_at)
    """, company)
    conn.commit()
    conn.close()


def list_funded(limit=20):
    conn = get_conn()
    rows = conn.execute("""
        SELECT company, amount, round_type, careers_url, found_at
        FROM funded_companies ORDER BY found_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_config():
    conn = get_conn()
    row = conn.execute("SELECT value FROM config WHERE key = 'search'").fetchone()
    conn.close()
    return json.loads(row[0]) if row else dict(DEFAULT_CONFIG)


def set_config(cfg):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('search', ?)",
                 (json.dumps(cfg),))
    conn.commit()
    conn.close()


def add_journal_entry(text, created_at):
    conn = get_conn()
    conn.execute("INSERT INTO journal (entry, created_at) VALUES (?, ?)", (text, created_at))
    conn.commit()
    conn.close()


def get_journal_entries(limit=30):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, entry, created_at FROM journal ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
