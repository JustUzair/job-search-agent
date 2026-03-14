import os
import re
import json
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
    "sections/objective.tex",
    "sections/experience.tex",
    "sections/skills.tex",
    "sections/projects.tex",
    "sections/achievements.tex",
    "sections/security.tex",
}

COPY_ONLY = {
    "resume.tex", "_header.tex", "TLCresume.sty",
    "sections/education.tex", "sections/certifications.tex",
    "sections/hobbies.tex", "sections/por.tex",
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
{jd[:2500]}

RESUME FILES:
{files_block}

RULES:
- Reorder bullets to surface most relevant experience first
- Rewrite objective.tex to speak directly to this role
- Reorder skills.tex so most relevant skills appear first
- Do NOT invent skills, experience, or tools
- Do NOT change company names, job titles, or dates
- Keep all LaTeX commands intact
- Return ONLY files that actually changed

Respond with ONLY a JSON object: {{"sections/objective.tex": "...full content...", ...}}
No markdown fences around the JSON."""


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


def tailor(job_id=None, url=None, raw_jd=None):
    files = load_resume_files()
    if not files:
        return {"error": f"No resume files found at {RESUME_DIR}. Check volume mount."}

    if job_id:
        job = db.get_job(job_id)
        if not job:
            return {"error": f"Job {job_id} not found"}
        title, company = job["title"], job["company"]
        jd = job["description"] if len(job["description"]) > 200 else fetch_jd(job["url"])
    elif url:
        title, company = "Role", url.split("/")[2] if url.count("/") >= 2 else "company"
        jd = fetch_jd(url)
    elif raw_jd:
        title, company, jd = "Role", "Company", raw_jd
    else:
        return {"error": "Need job_id, url, or raw_jd"}

    prompt = build_prompt(jd, title, company, files)

    # Use gpt-4o / claude-sonnet for tailoring — needs more reasoning than scoring
    original_model = os.environ.get("MODEL_NAME", "gpt-4o-mini")
    os.environ["MODEL_NAME"] = os.environ.get("TAILOR_MODEL", original_model)

    raw = llm.chat(prompt, max_tokens=4096, temperature=0.3)

    os.environ["MODEL_NAME"] = original_model  # restore

    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw).strip()

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

    return {
        "zip_path": zip_path,
        "out_dir": out_dir,
        "company": company,
        "title": title,
        "changed_files": list(updated_files.keys()),
    }
