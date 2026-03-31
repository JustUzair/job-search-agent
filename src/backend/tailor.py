import hashlib
import os
import re
import json
import subprocess
import zipfile
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

import db
import llm

IST = timezone(timedelta(hours=5, minutes=30))
RESUME_DIR = os.environ.get("RESUME_DIR", "/app/resume")
RESUME_OUT_DIR = "/app/data/resumes"

TAILOR_TARGETS = {
    "sections/summary.tex",      # ← was summary.tex
    "sections/experience.tex",
    "sections/skills.tex",
    "sections/projects.tex",
    "sections/achievements.tex",
    # "sections/security.tex",
}

COPY_ONLY = {
    "resume.tex", "_header.tex", "TLCresume.sty",
    "sections/education.tex", "sections/certifications.tex", "sections/por.tex",
    "sections/security.tex",
}


def _repair_latex_json(raw: str) -> str:
    """
    Best-effort repair of common LLM mistakes when embedding LaTeX inside JSON.

    Problems seen in the wild:
    1. LLM emits a single backslash instead of \\\\ (raw \\ in the JSON string),
       so sequences like \\textbf, \\section, \\begin appear as bare control chars.
    2. LLM uses actual newlines inside a JSON string value instead of \\n.
    3. Response is truncated – the JSON is simply cut off; we can't fix this,
       but we log a clear message so the caller knows to raise max_tokens.
    """
    # If it already parses, nothing to do.
    try:
        json.loads(raw)
        return raw
    except json.JSONDecodeError:
        pass

    # Strategy: locate each string value and fix un-escaped content inside it.
    # We do this by re-serializing via a regex that operates on the raw text.
    #
    # Pass 1: fix literal (unescaped) newlines inside JSON string values.
    # A JSON string value spans from an opening " (not preceded by \) to the
    # matching closing " (not preceded by \).  Newlines inside it are illegal.
    def _fix_newlines(m):
        # m.group(0) is the whole matched string literal including the quotes
        inner = m.group(1)
        inner = inner.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
        return '"' + inner + '"'

    # Regex: match a JSON string token (simplified – handles most real output)
    repaired = re.sub(
        r'"((?:[^"\\]|\\.)*)"',
        _fix_newlines,
        raw,
        flags=re.DOTALL,
    )

    try:
        json.loads(repaired)
        return repaired
    except json.JSONDecodeError:
        pass

    # If still broken, return original so the caller gets the real error
    return raw


def apply_edits(instructions: str, variant_name: str = "") -> dict:
    """Apply free-form resume edit instructions (no job context needed)."""
    files = load_resume_files()
    if not files:
        return {"error": f"No resume files found at {RESUME_DIR}. Check volume mount."}
    if not instructions.strip():
        return {"error": "instructions must not be empty"}

    target_content = {k: v for k, v in files.items() if k in TAILOR_TARGETS}
    files_block = "\n\n".join(
        f"### FILE: {path}\n```latex\n{content}\n```"
        for path, content in target_content.items()
    )

    prompt = f"""You are a resume editor. Apply the user's requested changes to these LaTeX resume files.

USER INSTRUCTIONS:
{instructions.strip()}

RESUME FILES:
{files_block}

RULES:
- Apply ONLY the changes the user explicitly asked for
- Do NOT invent skills, experience, or tools not already in the resume
- Do NOT change company names, job titles, or dates
- Keep all LaTeX commands intact
- Return ONLY the files that actually changed
- Pick ONLY 3 projects based on the job description
- Pick ONLY 3 best from the given professional experiences, the ones most relevant to the job description; remove or de-emphasize less relevant roles

Respond with ONLY a JSON object: {{"sections/summary.tex": "...full content...", ...}}
No markdown fences around the JSON."""

    original_model = os.environ.get("MODEL_NAME", "gpt-4o-mini")
    os.environ["MODEL_NAME"] = os.environ.get("TAILOR_MODEL", original_model)
    raw = llm.chat(prompt, max_tokens=16000, temperature=0.2)
    os.environ["MODEL_NAME"] = original_model

    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw).strip()
    raw = _repair_latex_json(raw)

    try:
        updated_files = json.loads(raw)
    except json.JSONDecodeError as e:
        return {"error": f"LLM returned invalid JSON: {e}\n{raw[:200]}"}

    updated_files = {k: v for k, v in updated_files.items() if k in TAILOR_TARGETS}
    if not updated_files:
        return {"error": "LLM returned no changed files. Try rephrasing your instructions."}

    os.makedirs(RESUME_OUT_DIR, exist_ok=True)
    ts = datetime.now(IST).strftime("%Y%m%d_%H%M")
    label = re.sub(r"[^\w\-]", "_", (variant_name or "manual_edit").lower())[:30]
    out_dir = os.path.join(RESUME_OUT_DIR, f"{label}_{ts}")
    os.makedirs(os.path.join(out_dir, "sections"), exist_ok=True)

    for rel_path in set(files) | set(updated_files):
        content = updated_files.get(rel_path) or files.get(rel_path, "")
        out_path = os.path.join(out_dir, rel_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            f.write(content)

    zip_path = make_zip(out_dir, label)
    pdf_path, compile_log = compile_pdf(out_dir)

    variant_id = hashlib.md5(f"{label}_{ts}".encode()).hexdigest()[:16]
    db.save_variant({
        "id": variant_id,
        "job_id": "",
        "company": "",
        "title": variant_name or "Manual edit",
        "variant_name": variant_name or f"edit_{ts}",
        "out_dir": out_dir,
        "zip_path": zip_path,
        "pdf_path": pdf_path,
        "changed_files": list(updated_files.keys()),
        "job_score": 0,
        "created_at": datetime.now(IST).isoformat(),
    })

    return {
        "variant_id": variant_id,
        "zip_path": zip_path,
        "pdf_path": pdf_path,
        "changed_files": list(updated_files.keys()),
        "compile_log": compile_log if not pdf_path else None,
    }


def refine_variant(variant_id: str, feedback: str) -> dict:
    """Apply feedback to an already-tailored variant and produce a new one."""
    variant = db.get_variant(variant_id)
    if not variant:
        return {"error": f"Variant {variant_id} not found"}

    out_dir = variant.get("out_dir", "")
    if not out_dir or not os.path.isdir(out_dir):
        return {"error": "Variant output directory not found on disk"}

    # Load files from the tailored variant (not master) so we iterate on what was already changed
    files = {}
    for rel_path in list(TAILOR_TARGETS) + list(COPY_ONLY):
        abs_path = os.path.join(out_dir, rel_path)
        if os.path.exists(abs_path):
            with open(abs_path) as f:
                files[rel_path] = f.read()

    if not files:
        return {"error": "No LaTeX files found in variant directory"}

    target_content = {k: v for k, v in files.items() if k in TAILOR_TARGETS}
    files_block = "\n\n".join(
        f"### FILE: {path}\n```latex\n{content}\n```"
        for path, content in target_content.items()
    )

    prompt = f"""You are a resume editor. Apply this feedback to the resume.

FEEDBACK:
{feedback.strip()}

CURRENT RESUME FILES:
{files_block}

RULES:
- Apply ONLY the changes requested in the feedback
- Do NOT invent skills, experience, or tools not already in the resume
- Do NOT change company names, job titles, or dates
- Keep all LaTeX commands intact
- Return ONLY the files that actually changed

Respond with ONLY a JSON object: {{"sections/summary.tex": "...full content...", ...}}
No markdown fences around the JSON."""

    original_model = os.environ.get("MODEL_NAME", "gpt-4o-mini")
    os.environ["MODEL_NAME"] = os.environ.get("TAILOR_MODEL", original_model)
    raw = llm.chat(prompt, max_tokens=16000, temperature=0.2)
    os.environ["MODEL_NAME"] = original_model

    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw).strip()
    raw = _repair_latex_json(raw)

    try:
        updated_files = json.loads(raw)
    except json.JSONDecodeError as e:
        return {"error": f"LLM returned invalid JSON: {e}\n{raw[:200]}"}

    updated_files = {k: v for k, v in updated_files.items() if k in TAILOR_TARGETS}
    if not updated_files:
        return {"error": "LLM returned no changed files. Try rephrasing your feedback."}

    ts = datetime.now(IST).strftime("%Y%m%d_%H%M")
    # Strip any previous timestamp suffix to keep directory names clean
    base_label = re.sub(r"_\d{8}_\d{4}(_r\d{8}_\d{4})*$", "", os.path.basename(out_dir))[:30]
    new_out_dir = os.path.join(RESUME_OUT_DIR, f"{base_label}_r{ts}")
    os.makedirs(os.path.join(new_out_dir, "sections"), exist_ok=True)

    for rel_path in set(files) | set(updated_files):
        content = updated_files.get(rel_path) or files.get(rel_path, "")
        out_path = os.path.join(new_out_dir, rel_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            f.write(content)

    zip_path = make_zip(new_out_dir, base_label)
    pdf_path, compile_log = compile_pdf(new_out_dir)

    new_variant_id = hashlib.md5(f"{base_label}_r{ts}".encode()).hexdigest()[:16]
    db.save_variant({
        "id": new_variant_id,
        "job_id": variant.get("job_id", ""),
        "company": variant.get("company", ""),
        "title": variant.get("title", ""),
        "variant_name": f"{variant.get('variant_name', 'variant')}_r{ts}",
        "out_dir": new_out_dir,
        "zip_path": zip_path,
        "pdf_path": pdf_path,
        "changed_files": list(updated_files.keys()),
        "job_score": variant.get("job_score", 0),
        "created_at": datetime.now(IST).isoformat(),
    })

    return {
        "variant_id": new_variant_id,
        "zip_path": zip_path,
        "pdf_path": pdf_path,
        "company": variant.get("company", ""),
        "changed_files": list(updated_files.keys()),
        "compile_log": compile_log if not pdf_path else None,
    }


def fetch_jd(url):
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["nav", "header", "footer", "script", "style"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)[:3000]
    except Exception as e:
        return f"Could not fetch: {e}"


def load_resume_files():
    files = {}
    if not os.path.isdir(RESUME_DIR):
        return files
    for rel_path in [*TAILOR_TARGETS, *COPY_ONLY]:
        abs_path = os.path.join(RESUME_DIR, rel_path)
        if os.path.exists(abs_path):
            with open(abs_path) as f:
                files[rel_path] = f.read()
    return files


def build_prompt(jd, title, company, files):
    target_content = {k: v for k, v in files.items() if k in TAILOR_TARGETS}
    files_block = "\n\n".join(
        f"### FILE: {path}\n```latex\n{content}\n```"
        for path, content in target_content.items()
    )
    return f"""You are a resume editor. Tailor these LaTeX files for this specific job.

JOB: {title} at {company}

JOB DESCRIPTION:
{jd[:1500]}

RESUME FILES:
{files_block}

JSON OUTPUT RULES (critical — invalid JSON causes a hard failure):
- Respond with ONLY a raw JSON object. No markdown fences, no preamble, no trailing text.
- Every backslash in LaTeX MUST be doubled in the JSON string: \\textbf → \\\\textbf, \\begin → \\\\begin, \\section → \\\\section, etc.
- Every newline inside a JSON string value MUST be written as the two-character sequence \\n, NOT a literal line break.
- Double curly braces in LaTeX (e.g. \\section{{...}}) stay as-is; they are valid JSON string content.
- Return ONLY the files that actually changed.

TAILORING RULES:
- Reorder bullets to surface most relevant experience first
- Rewrite summary.tex to speak directly to this role, BUT DO NOT LIE ABOUT EXPERIENCES OR PREVIOUS WORK
- Reorder skills.tex so most relevant skills appear first
- Do NOT invent skills, experience, or tools
- Do NOT change company names, job titles, or dates
- Keep all LaTeX commands intact
- Escape special characters (e.g. & to \\&, % to \\%, $ to \\$) unless part of a command or rendering symbols
- Pick ONLY 3 projects based on the job description; remove entire 'resumeProjectHeading' blocks for others
- Keep \\section header and surrounding vspace commands unchanged in projects.tex

Respond with ONLY a JSON object: {{"sections/summary.tex": "...full content...", ...}}"""


def make_zip(out_dir, company):
    """Zip the output folder so it can be uploaded directly to Overleaf."""
    zip_path = out_dir + ".zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, fnames in os.walk(out_dir):
            for fname in fnames:
                abs_path = os.path.join(root, fname)
                arcname = os.path.relpath(abs_path, out_dir)
                zf.write(abs_path, arcname)
    return zip_path


def compile_pdf(out_dir: str) -> tuple[str, str]:
    """Run latexmk to compile resume.tex to PDF. Returns (pdf_path, error_log)."""
    resume_tex = os.path.join(out_dir, "resume.tex")
    if not os.path.exists(resume_tex):
        return "", "resume.tex not found"
    try:
        result = subprocess.run(
            ["latexmk", "-pdf", "-interaction=nonstopmode", "-outdir=.", "resume.tex"],
            cwd=out_dir,
            capture_output=True,
            timeout=60,
            text=True,
        )
        pdf_path = os.path.join(out_dir, "resume.pdf")
        if os.path.exists(pdf_path):
            return pdf_path, ""
        return "", f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
    except Exception as e:
        return "", str(e)


FIT_THRESHOLD = 35  # below this score, warn before tailoring


def check_fit(jd: str, title: str, company: str) -> tuple[int, str]:
    """Quick scoring call to assess fit before running the full tailor prompt."""
    candidate_profile = db.get_profile()
    data = llm.chat_json(
        f"""Score this job for the candidate (0-100).

CANDIDATE:
{candidate_profile}

JOB:
Title: {title}
Company: {company}
Description: {jd[:1000]}

Rules:
- Score 0 if role requires physical presence (onsite/in-office)
- Score 0 if requires 5+ years experience for a 2-year candidate
- Score based on tech stack overlap, seniority match, remote availability

Reply ONLY valid JSON: {{"score": <int>, "reason": "<max 120 chars>"}}""",
        max_tokens=80,
    )
    return int(data.get("score", 0)), str(data.get("reason", "no reason returned"))[:120]


def tailor(job_id=None, url=None, raw_jd=None, variant_name="", force=False):
    files = load_resume_files()
    if not files:
        return {"error": f"No resume files found at {RESUME_DIR}. Check volume mount."}

    if job_id:
        job = db.get_job(job_id)
        if not job:
            return {"error": f"Job {job_id} not found"}
        title, company = job["title"], job["company"]
        jd = job["description"] if len(job["description"]) > 200 else fetch_jd(job["url"])
        job_score = job.get("score", 0)
        # Use existing score if already computed, otherwise run a fresh fit check
        existing_score = job.get("score", -1)
        if existing_score >= 0:
            fit_score, fit_reason = existing_score, job.get("reason", "")
        else:
            fit_score, fit_reason = check_fit(jd, title, company)
    elif url:
        title, company = "Role", url.split("/")[2] if url.count("/") >= 2 else "company"
        jd = fetch_jd(url)
        job_score = 0
        fit_score, fit_reason = check_fit(jd, title, company)
    elif raw_jd:
        title, company, jd = "Role", "Company", raw_jd
        job_score = 0
        fit_score, fit_reason = check_fit(jd, title, company)
    else:
        return {"error": "Need job_id, url, or raw_jd"}

    # Warn if poor fit, unless the user explicitly forced past the warning
    if fit_score < FIT_THRESHOLD and not force:
        return {
            "fit_warning": True,
            "score": fit_score,
            "reason": fit_reason,
        }

    prompt = build_prompt(jd, title, company, files)

    # Use gpt-4o / claude-sonnet for tailoring — needs more reasoning than scoring
    original_model = os.environ.get("MODEL_NAME", "gpt-4o-mini")
    os.environ["MODEL_NAME"] = os.environ.get("TAILOR_MODEL", original_model)

    raw = llm.chat(prompt, max_tokens=16000, temperature=0.3)

    os.environ["MODEL_NAME"] = original_model  # restore

    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw).strip()
    raw = _repair_latex_json(raw)

    try:
        updated_files = json.loads(raw)
    except json.JSONDecodeError as e:
        return {"error": f"LLM returned invalid JSON: {e}\n{raw[:200]}"}

    updated_files = {k: v for k, v in updated_files.items() if k in TAILOR_TARGETS}

    # Write output folder
    os.makedirs(RESUME_OUT_DIR, exist_ok=True)
    safe = re.sub(r"[^\w\-]", "_", company.lower())[:30]
    ts = datetime.now(IST).strftime("%Y%m%d_%H%M")
    out_dir = os.path.join(RESUME_OUT_DIR, f"{safe}_{ts}")
    os.makedirs(os.path.join(out_dir, "sections"), exist_ok=True)

    for rel_path in set(files) | set(updated_files):
        content = updated_files.get(rel_path) or files.get(rel_path, "")
        out_path = os.path.join(out_dir, rel_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            f.write(content)

    zip_path = make_zip(out_dir, company)

    pdf_path, compile_log = compile_pdf(out_dir)

    variant_id = hashlib.md5(f"{company}_{ts}".encode()).hexdigest()[:16]

    db.save_variant({
        "id": variant_id,
        "job_id": job_id or "",
        "company": company,
        "title": title,
        "variant_name": variant_name or f"{safe}_{ts}",
        "out_dir": out_dir,
        "zip_path": zip_path,
        "pdf_path": pdf_path,
        "changed_files": list(updated_files.keys()),
        "job_score": job_score,
        "created_at": datetime.now(IST).isoformat(),
    })

    return {
        "variant_id": variant_id,
        "zip_path": zip_path,
        "pdf_path": pdf_path,
        "out_dir": out_dir,
        "company": company,
        "title": title,
        "changed_files": list(updated_files.keys()),
        "compile_log": compile_log if not pdf_path else None,
    }