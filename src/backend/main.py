"""
OpenClaw — FastAPI backend
Run: uvicorn src.backend.main:app --reload --port 8000
"""
import asyncio
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Add src/backend to path so imports work
sys.path.insert(0, str(Path(__file__).parent))
import db
import scraper as scraper_mod
import tailor as tailor_mod
import llm

from apscheduler.schedulers.asyncio import AsyncIOScheduler

IST = timezone(timedelta(hours=5, minutes=30))

# In-memory scrape state
_scrape_state = {"running": False, "last_result": None, "last_run": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(_scheduled_scrape, trigger="cron", hour=8, minute=0)
    scheduler.add_job(_poll_batches_bg, trigger="interval", minutes=5, id="batch_poll")
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="OpenClaw", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _scheduled_scrape():
    await _run_scrape_bg(None)


async def _run_scrape_bg(sources):
    _scrape_state["running"] = True
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: scraper_mod.run_scrape(sources)
        )
        _scrape_state["last_result"] = result
        _scrape_state["last_run"] = datetime.now(IST).isoformat()
    finally:
        _scrape_state["running"] = False


async def _poll_batches_bg():
    """Called every 5 min by scheduler to check pending LLM batches."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, scraper_mod.poll_pending_batches)


# ── Pydantic models ───────────────────────────────────────────────────────────

class StatusUpdate(BaseModel):
    status: str


class ScrapeRequest(BaseModel):
    sources: Optional[list] = None


class TailorRequest(BaseModel):
    job_id: Optional[str] = None
    url: Optional[str] = None
    raw_jd: Optional[str] = None
    variant_name: Optional[str] = ""
    force: bool = False


class JournalEntry(BaseModel):
    entry: str


# ── Jobs ──────────────────────────────────────────────────────────────────────

@app.get("/api/jobs")
def get_jobs(status: str = "new", limit: int = 20, offset: int = 0):
    jobs = db.list_jobs(status=status, limit=limit, offset=offset)
    total = db.count_jobs(status=status)
    return {"jobs": jobs, "total": total}


@app.get("/api/jobs/all")
def get_all_jobs(
    limit: int = 50,
    offset: int = 0,
    source: Optional[str] = None,
    status: Optional[str] = None,
):
    jobs = db.list_all_jobs(limit=limit, offset=offset, source=source, status=status)
    total = db.count_all_jobs(source=source, status=status)
    return {"jobs": jobs, "total": total}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/api/jobs/{job_id}/status")
def update_job_status(job_id: str, body: StatusUpdate):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    allowed = {"applied", "skipped", "new", "tailored"}
    if body.status not in allowed:
        raise HTTPException(status_code=400, detail=f"status must be one of {allowed}")
    db.set_status(job_id, body.status)
    return {"ok": True}


# ── Scrape ────────────────────────────────────────────────────────────────────

@app.post("/api/scrape")
async def start_scrape(body: ScrapeRequest, background_tasks: BackgroundTasks):
    if _scrape_state["running"]:
        return {"status": "already_running"}
    background_tasks.add_task(_run_scrape_bg, body.sources)
    return {"status": "started"}


@app.get("/api/scrape/status")
def scrape_status():
    return {
        "running": _scrape_state["running"],
        "last_result": _scrape_state["last_result"],
        "last_run": _scrape_state["last_run"],
    }


# ── Batches ───────────────────────────────────────────────────────────────────

@app.get("/api/batches")
def list_batches():
    pending = db.get_pending_batches()
    return {"pending": pending, "count": len(pending)}


@app.post("/api/batches/poll")
async def poll_batches(background_tasks: BackgroundTasks):
    """Trigger immediate batch polling (also runs every 5 min automatically)."""
    background_tasks.add_task(_poll_batches_bg)
    return {"status": "polling"}


# ── Tailor ────────────────────────────────────────────────────────────────────

@app.post("/api/tailor")
def run_tailor(body: TailorRequest):
    if not body.job_id and not body.url and not body.raw_jd:
        raise HTTPException(status_code=400, detail="Provide job_id, url, or raw_jd")
    result = tailor_mod.tailor(
        job_id=body.job_id,
        url=body.url,
        raw_jd=body.raw_jd,
        variant_name=body.variant_name or "",
        force=body.force,
    )
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


# ── Resume editor ────────────────────────────────────────────────────────────

class ResumeEditRequest(BaseModel):
    instructions: str
    variant_name: Optional[str] = ""


@app.post("/api/resume/edit")
def resume_edit(body: ResumeEditRequest):
    if not body.instructions.strip():
        raise HTTPException(status_code=400, detail="instructions must not be empty")
    result = tailor_mod.apply_edits(
        instructions=body.instructions,
        variant_name=body.variant_name or "",
    )
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


# ── Variants ──────────────────────────────────────────────────────────────────

class RefineRequest(BaseModel):
    feedback: str


@app.post("/api/variants/{variant_id}/refine")
def refine_variant(variant_id: str, body: RefineRequest):
    if not body.feedback.strip():
        raise HTTPException(status_code=400, detail="feedback must not be empty")
    result = tailor_mod.refine_variant(variant_id, body.feedback)
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


@app.get("/api/variants")
def list_variants():
    return {"variants": db.list_variants(limit=50)}


@app.get("/api/variants/{variant_id}/zip")
def get_variant_zip(variant_id: str):
    variant = db.get_variant(variant_id)
    if not variant:
        raise HTTPException(status_code=404, detail="Variant not found")
    zip_path = variant.get("zip_path", "")
    if not zip_path or not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="Zip file not found")
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=os.path.basename(zip_path),
    )


@app.get("/api/variants/{variant_id}/pdf")
def get_variant_pdf(variant_id: str):
    variant = db.get_variant(variant_id)
    if not variant:
        raise HTTPException(status_code=404, detail="Variant not found")
    pdf_path = variant.get("pdf_path", "")
    if not pdf_path or not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF not found or not compiled")
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=os.path.basename(pdf_path),
    )


# ── Funded companies ──────────────────────────────────────────────────────────

@app.get("/api/funded")
def get_funded(limit: int = 20):
    return {"companies": db.list_funded(limit=limit)}


# ── Journal ───────────────────────────────────────────────────────────────────

@app.get("/api/journal")
def get_journal(limit: int = 30, offset: int = 0):
    entries = db.get_journal_entries(limit=limit, offset=offset)
    return {"entries": entries}


@app.post("/api/journal")
def add_journal(body: JournalEntry):
    if not body.entry.strip():
        raise HTTPException(status_code=400, detail="entry must not be empty")
    created_at = datetime.now(IST).isoformat()
    db.add_journal_entry(body.entry.strip(), created_at)
    return {"ok": True, "created_at": created_at}


# ── Resume diff ───────────────────────────────────────────────────────────────

@app.post("/api/resumediff")
def resume_diff():
    entries = db.get_journal_entries(limit=30)
    if not entries:
        raise HTTPException(status_code=422, detail="No journal entries yet. Add entries first.")
    journal_text = "\n".join(
        f"[{e['created_at'][:10]}] {e['entry']}" for e in reversed(entries)
    )
    prompt = f"""You are an expert Resume Advisor specializing in Full Stack Engineering and AI Development.

    Below are the user's recent work journal entries:

    {journal_text}

    The user's current resume is focused on Full Stack Development, specifically:
    - AI & RAG Systems: Building and deploying "Tessera" (RAG agent) on Vercel.
    - Backend & Rust: Developing Rust Rocket and Axum-based services, including real-time chat rooms.
    - Frontend & Dashboards: Creating the Covalent Vibe Dashboard using Next.js and Tailwind CSS.
    - DevRel/Solutions Engineering: Technical documentation and developer advocacy at BuildBear.

    Based on the journal entries, suggest specific resume updates:

    1. NEW BULLET POINTS: Provide exact LaTeX \item text for the "Projects" or "Experience" sections. Focus on engineering challenges, performance metrics, and deployment (Vercel, Railway).
    2. STRENGTHENING EXISTING BULLETS: Suggest ways to improve current bullet points by adding quantifiable results (e.g., latency reduction in RAG pipelines or API response times).
    3. TECHNICAL SKILLS: Identify new frameworks, libraries (e.g., LangChain, Axum, Rocket), or tools mentioned in the journal that should be added to the "Technical Skills" section.

    CRITICAL CONSTRAINT: Do not include or suggest updates related to Web3 security audits, smart contract vulnerabilities, or bug bounty hunting. This resume is strictly for Full Stack and AI Engineering roles.

    Format your response as a clear numbered list."""
    suggestions = llm.chat(prompt, max_tokens=800, temperature=0.4)
    return {"suggestions": suggestions}


# ── Config ────────────────────────────────────────────────────────────────────

@app.get("/api/config")
def get_config():
    return db.get_config()


@app.put("/api/config")
def put_config(body: Dict[str, Any]):
    db.set_config(body)
    return {"ok": True}


# ── Candidate profile ─────────────────────────────────────────────────────────

class ProfileBody(BaseModel):
    profile: str


@app.get("/api/profile")
def get_profile():
    return {"profile": db.get_profile()}


@app.put("/api/profile")
def put_profile(body: ProfileBody):
    if not body.profile.strip():
        raise HTTPException(status_code=400, detail="profile must not be empty")
    db.set_profile(body.profile.strip())
    return {"ok": True}


@app.post("/api/profile/sync-from-journal")
def sync_profile_from_journal():
    entries = db.get_journal_entries(limit=30)
    if not entries:
        raise HTTPException(status_code=422, detail="No journal entries yet.")
    journal_text = "\n".join(
        f"[{e['created_at'][:10]}] {e['entry']}" for e in reversed(entries)
    )
    current_profile = db.get_profile()
    prompt = f"""You are a resume advisor. Update this candidate profile with new skills and experience from their recent work journal.

CURRENT PROFILE:
{current_profile}

RECENT JOURNAL ENTRIES:
{journal_text}

INSTRUCTIONS:
- Add any new technologies, tools, or skills mentioned in the journal that aren't in the profile
- Update "Recent work" with notable accomplishments from the journal
- Keep all existing info that is still relevant
- Keep the same concise format — this text is used as context for AI job scoring
- Do NOT invent anything not mentioned in the journal or existing profile
- Return ONLY the updated profile text, no commentary

Updated profile:"""
    updated = llm.chat(prompt, max_tokens=600, temperature=0.2)
    return {"profile": updated.strip()}


@app.get("/api/sources")
async def get_sources():
    return db.get_distinct_sources()


# ── Static files (React SPA) ──────────────────────────────────────────────────

FRONTEND_DIST = Path(__file__).parent.parent.parent / "src" / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=str(FRONTEND_DIST / "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        return FileResponse(str(FRONTEND_DIST / "index.html"))


@app.get("/api/resume/compile-test")
def resume_compile_test():
    """
    Dry-run: copies the master resume into a temp dir and compiles it with latexmk.
    No LLM involved. Use this to verify LaTeX packages and file mounts are correct.
    """
    import tempfile, shutil
    files = tailor_mod.load_resume_files()
    if not files:
        raise HTTPException(status_code=500, detail=f"No resume files found at {tailor_mod.RESUME_DIR}")

    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "sections"), exist_ok=True)
        for rel_path, content in files.items():
            out = os.path.join(tmp, rel_path)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "w") as f:
                f.write(content)

        pdf_path, log = tailor_mod.compile_pdf(tmp)
        if pdf_path:
            return {"ok": True, "files_loaded": list(files.keys())}
        return {
            "ok": False,
            "files_loaded": list(files.keys()),
            "log": log[-3000:],   # last 3000 chars of latexmk output
        }