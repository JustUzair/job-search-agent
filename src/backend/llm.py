"""
Thin wrapper around OpenAI and Anthropic so the rest of the code
doesn't care which provider is active.

.env config:
  MODEL_PROVIDER=openai       # openai | anthropic
  MODEL_API_KEY=sk-...
  MODEL_NAME=gpt-4o-mini      # or claude-haiku-4-5-20251001 etc.
"""
import os
import json
import re

PROVIDER = os.environ.get("MODEL_PROVIDER", "openai").lower()
API_KEY  = os.environ.get("MODEL_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
MODEL    = os.environ.get("MODEL_NAME", "gpt-4o-mini")


def chat(prompt: str, max_tokens: int = 200, temperature: float = 0.2) -> str:
    """Send a single-turn prompt, return the assistant text."""
    if PROVIDER == "anthropic":
        return _anthropic(prompt, max_tokens, temperature)
    return _openai(prompt, max_tokens, temperature)


def _openai(prompt, max_tokens, temperature):
    from openai import OpenAI
    client = OpenAI(api_key=API_KEY)
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip()


def _anthropic(prompt, max_tokens, temperature):
    import anthropic
    client = anthropic.Anthropic(api_key=API_KEY)
    msg = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def chat_json(prompt: str, max_tokens: int = 200) -> dict:
    """Like chat() but strips fences and parses JSON, returns {} on failure."""
    raw = chat(prompt, max_tokens=max_tokens, temperature=0.1)
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw).strip()
    try:
        return json.loads(raw)
    except Exception:
        return {}


# ── Batch scoring (Anthropic Message Batches API — 50% cheaper) ──────────

def create_scoring_batch(jobs: list, candidate_profile: str) -> str | None:
    """
    Submit all jobs for scoring in a single Anthropic batch request.
    Returns the batch_id (string) or None if batching isn't available.
    Falls back to None for non-Anthropic providers so caller can use sync scoring.
    """
    if PROVIDER != "anthropic" or not jobs:
        return None

    import anthropic
    client = anthropic.Anthropic(api_key=API_KEY)

    requests = []
    for job in jobs:
        prompt = _build_score_prompt(job, candidate_profile)
        requests.append({
            "custom_id": job["id"],
            "params": {
                "model": MODEL,
                "max_tokens": 80,
                "temperature": 0.1,
                "messages": [{"role": "user", "content": prompt}],
            },
        })

    batch = client.messages.batches.create(requests=requests)
    return batch.id


def poll_batch(batch_id: str) -> dict | None:
    """
    Check batch status. Returns dict with 'status' and 'results' (if done).
    Results is a list of {custom_id, score, reason} dicts.
    """
    if PROVIDER != "anthropic":
        return None

    import anthropic
    client = anthropic.Anthropic(api_key=API_KEY)

    batch = client.messages.batches.retrieve(batch_id)
    if batch.processing_status != "ended":
        return {"status": "in_progress", "results": []}

    results = []
    for entry in client.messages.batches.results(batch_id):
        custom_id = entry.custom_id
        score, reason = 0, ""
        if entry.result.type == "succeeded":
            raw_text = entry.result.message.content[0].text.strip()
            raw_text = re.sub(r"^```[a-z]*\n?", "", raw_text)
            raw_text = re.sub(r"\n?```$", "", raw_text).strip()
            try:
                data = json.loads(raw_text)
                score = int(data.get("score", 0))
                reason = str(data.get("reason", ""))[:120]
            except Exception:
                reason = "parse error"
        else:
            reason = f"batch error: {entry.result.type}"
        results.append({"custom_id": custom_id, "score": score, "reason": reason})

    return {"status": "completed", "results": results}


def _build_score_prompt(job: dict, candidate_profile: str) -> str:
    desc = (job.get("description") or "")[:1200]
    return f"""Score this job for the candidate (0-100).

CANDIDATE:
{candidate_profile}

JOB:
Title: {job.get('title', '?')}
Company: {job.get('company', '?')}
Work type: {job.get('work_type', '?')}
Location: {job.get('location', '?')}
Description: {desc}

Rules:
- Score 0 if the role requires physical presence (onsite/in-office) anywhere
- Score 0 if it requires 5+ years experience for a junior/mid candidate
- Score based on tech stack overlap, seniority match, remote availability

Reply ONLY valid JSON: {{"score": <int>, "reason": "<max 100 chars>"}}"""
