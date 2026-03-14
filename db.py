import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH", "/app/data/jobs.db")


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
            score       INTEGER,
            reason      TEXT,
            status      TEXT DEFAULT 'new',
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
    """)
    conn.commit()
    conn.close()


def job_exists(job_id: str) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    return row is not None


def save_job(job: dict):
    conn = get_conn()
    conn.execute("""
        INSERT OR IGNORE INTO jobs
        (id, source, title, company, url, description, score, reason, status, found_at)
        VALUES (:id, :source, :title, :company, :url, :description,
                :score, :reason, :status, :found_at)
    """, job)
    conn.commit()
    conn.close()


def list_jobs(status="new", limit=20) -> list[dict]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT id, title, company, url, score, reason, source, found_at
        FROM jobs WHERE status = ?
        ORDER BY score DESC LIMIT ?
    """, (status, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_job(job_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def set_status(job_id: str, status: str):
    conn = get_conn()
    conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
    conn.commit()
    conn.close()


def save_funded_company(company: dict):
    conn = get_conn()
    conn.execute("""
        INSERT OR IGNORE INTO funded_companies
        (id, company, amount, round_type, careers_url, found_at)
        VALUES (:id, :company, :amount, :round_type, :careers_url, :found_at)
    """, company)
    conn.commit()
    conn.close()


def list_funded(limit=20) -> list[dict]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT company, amount, round_type, careers_url, found_at
        FROM funded_companies
        ORDER BY found_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
