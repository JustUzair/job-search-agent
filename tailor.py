import os
import re
import json
import shutil
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from openai import OpenAI

import db

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
RESUME_DIR = os.environ.get("RESUME_DIR", "/app/resume")   # mounted from your Mac
RESUME_OUT_DIR = "/app/data/resumes"

# Files GPT is allowed to modify
TAILOR_TARGETS = {
    "sections/objective.tex",
    "sections/experience.tex",
    "sections/skills.tex",
    "sections/projects.tex",
    "sections/achievements.tex",
    "sections/security.tex",
}

# Files copied as-is (structure/style, never modified)
COPY_ONLY = {
    "resume.tex",
    "_header.tex",
    "TLCresume.sty",
    "sections/education.tex",
    "sections/certifications.tex",
    "sections/hobbies.tex",
    "sections/por.tex",
}


def fetch_jd(url: str) -> str:
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["nav", "header", "footer", "script", "style"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)[:3000]
    except Exception as e:
        return f"Could not fetch: {e}"


def load_resume_files() -> dict[str, str]:
    """Read all known .tex files from the resume directory."""
    files = {}
    if not os.path.isdir(RESUME_DIR):
        return files
    for rel_path in [*TAILOR_TARGETS, *COPY_ONLY]:
        abs_path = os.path.join(RESUME_DIR, rel_path)
        if os.path.exists(abs_path):
            with open(abs_path) as f:
                files[rel_path] = f.read()
    return files


def build_prompt(jd: str, title: str, company: str, files: dict[str, str]) -> str:
    target_content = {k: v for k, v in files.items() if k in TAILOR_TARGETS}
    files_block = "\n\n".join(
        f"### FILE: {path}\n```latex\n{content}\n```"
        for path, content in target_content.items()
    )
    return f"""You are a resume editor. Tailor these LaTeX resume files for a specific job.

JOB: {title} at {company}

JOB DESCRIPTION:
{jd[:2500]}

RESUME FILES:
{files_block}

INSTRUCTIONS:
- Reorder bullet points within each job/project to surface the most relevant work first
- In objective.tex: rewrite the objective to speak directly to this role/company
- In skills.tex: reorder skill groups so the most relevant ones appear first
- Surface bullets matching the JD's tech stack or responsibilities
- Do NOT invent experience, skills, or tools the candidate doesn't already have
- Do NOT change company names, job titles, dates, or institution names
- Keep all LaTeX commands, environments, and formatting intact
- Only return files that actually changed — skip files that need no modifications

Respond with ONLY a JSON object mapping file paths to their new full content.
No explanation, no markdown fences around the JSON itself.
Example:
{{
  "sections/objective.tex": "...full new content...",
  "sections/skills.tex": "...full new content..."
}}"""


def save_tailored(company: str, original_files: dict[str, str], updated_files: dict[str, str]) -> str:
    """Write a complete resume folder with tailored files merged in. Returns output dir path."""
    os.makedirs(RESUME_OUT_DIR, exist_ok=True)
    safe = re.sub(r"[^\w\-]", "_", company.lower())[:30]
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    out_dir = os.path.join(RESUME_OUT_DIR, f"{safe}_{ts}")
    os.makedirs(os.path.join(out_dir, "sections"), exist_ok=True)

    all_paths = set(original_files.keys()) | set(updated_files.keys())
    for rel_path in all_paths:
        content = updated_files.get(rel_path) or original_files.get(rel_path, "")
        out_path = os.path.join(out_dir, rel_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            f.write(content)

    return out_dir


def tailor(job_id: str | None = None, url: str | None = None, raw_jd: str | None = None) -> dict:
    if not OPENAI_API_KEY:
        return {"error": "OPENAI_API_KEY not set"}

    files = load_resume_files()
    if not files:
        return {"error": f"No resume files found at {RESUME_DIR}. Check your volume mount."}

    client = OpenAI(api_key=OPENAI_API_KEY)

    # Resolve JD
    if job_id:
        job = db.get_job(job_id)
        if not job:
            return {"error": f"Job {job_id} not in DB"}
        title, company = job["title"], job["company"]
        jd = job["description"] if len(job["description"]) > 200 else fetch_jd(job["url"])
    elif url:
        title = "Role"
        company = url.split("/")[2] if url.count("/") >= 2 else "company"
        jd = fetch_jd(url)
    elif raw_jd:
        title, company, jd = "Role", "Company", raw_jd
    else:
        return {"error": "Need job_id, url, or raw_jd"}

    prompt = build_prompt(jd, title, company, files)

    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.3,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw).strip()

    try:
        updated_files: dict[str, str] = json.loads(raw)
    except json.JSONDecodeError as e:
        return {"error": f"GPT returned invalid JSON: {e}\nRaw output: {raw[:300]}"}

    # Only accept paths we know about — never write arbitrary files
    updated_files = {k: v for k, v in updated_files.items() if k in TAILOR_TARGETS}

    out_dir = save_tailored(company, files, updated_files)

    return {
        "out_dir": out_dir,
        "company": company,
        "title": title,
        "changed_files": list(updated_files.keys()),
    }
