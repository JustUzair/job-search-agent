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

# Set LLM_VERBOSE=true in .env to see raw model output before JSON parsing
LLM_VERBOSE = os.environ.get("LLM_VERBOSE", "").lower() in ("1", "true", "yes")
PROVIDER = os.environ.get("MODEL_PROVIDER", "ollama").lower()
API_KEY  = os.environ.get("MODEL_API_KEY", "ollama") or os.environ.get("OPENAI_API_KEY", "") # ollama doesnt need an api key
MODEL    = os.environ.get("MODEL_NAME", "gpt-oss:20b-cloud")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434") # cloud hosted or local model

def chat(prompt: str, max_tokens: int = 200, temperature: float = 0.2) -> str:
    """Send a single-turn prompt, return the assistant text."""
    if PROVIDER == "anthropic":
        return _anthropic(prompt, max_tokens, temperature)
    if PROVIDER == "ollama":
        return _ollama(prompt)
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

def _ollama(prompt):
    """Call a locally-running Ollama instance via its OpenAI-compatible endpoint."""
    from ollama import Client
    from ollama import chat
    client = Client(
        host=OLLAMA_BASE_URL
    )
    resp = client.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        think=False,
        stream=False,
    )
    return resp.message.content


def chat_json(prompt: str, max_tokens: int = 200) -> dict:
    """Like chat() but strips fences and parses JSON, returns {} on failure."""
    raw = chat(prompt, max_tokens=max_tokens, temperature=0.1)

    if LLM_VERBOSE:
        preview = raw.replace("\n", " ").strip()
        print(f"  [llm:raw]   {preview[:300]}")

    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw).strip()
    try:
        return json.loads(raw)
    except Exception as e:
        if LLM_VERBOSE:
            print(f"  [llm:parse_fail]  {e}  →  {raw[:200]}")
        return {}


# ── Batch scoring (Anthropic Message Batches API — 50% cheaper) ──────────

def create_scoring_batch(jobs: list, candidate_profile: str) -> str | None:
    """Submit jobs for batch scoring via Anthropic or OpenAI.
    Returns batch_id or None if batching unavailable.
    """
    if not jobs:
        return None
    if PROVIDER == "anthropic":
        return _create_anthropic_batch(jobs, candidate_profile)
    if PROVIDER == "openai":
        return _create_openai_batch(jobs, candidate_profile)
    if PROVIDER == "ollama":
        return _create_ollama_batch(jobs, candidate_profile)
    return None

def _create_ollama_batch(jobs, candidate_profile):
    """
    Simulates a batch API for Ollama by running concurrent requests.
    Returns a special string 'ollama_local_sync' plus the results JSON.
    """
    import concurrent.futures
    import json
    import re

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_to_job = {}
        for job in jobs:
            prompt = _build_score_prompt(job, candidate_profile)
            future = executor.submit(_ollama, prompt)  # only one argument
            future_to_job[future] = job

        for future in concurrent.futures.as_completed(future_to_job):
            job = future_to_job[future]
            custom_id = job.get("id")
            try:
                raw_text = future.result()
                # Clean JSON
                raw_text = re.sub(r"^```[a-z]*\n?", "", raw_text)
                raw_text = re.sub(r"\n?```$", "", raw_text).strip()
                data = json.loads(raw_text)
                results.append({
                    "custom_id": custom_id,
                    "score": int(data.get("score", 0)),
                    "reason": str(data.get("reason", ""))[:120]
                })
            except Exception as e:
                results.append({
                    "custom_id": custom_id,
                    "score": 0,
                    "reason": f"Ollama error: {str(e)}"
                })

    # Return a marker that the batch is done and include the results
    return f"LOCAL_BATCH_DONE:{json.dumps(results)}"
    

def _create_anthropic_batch(jobs, candidate_profile):
    import anthropic
    client = anthropic.Anthropic(api_key=API_KEY)
    reqs = []
    for job in jobs:
        prompt = _build_score_prompt(job, candidate_profile)
        reqs.append({
            "custom_id": job["id"],
            "params": {
                "model": MODEL,
                "max_tokens": 80,
                "temperature": 0.1,
                "messages": [{"role": "user", "content": prompt}],
            },
        })
    batch = client.messages.batches.create(requests=reqs)
    return batch.id


def _create_openai_batch(jobs, candidate_profile):
    """OpenAI Batch API: write JSONL → upload file → create batch → return batch_id."""
    import tempfile
    from openai import OpenAI
    client = OpenAI(api_key=API_KEY)

    # Write JSONL to temp file
    lines = []
    for job in jobs:
        prompt = _build_score_prompt(job, candidate_profile)
        lines.append(json.dumps({
            "custom_id": job["id"],
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": MODEL,
                "max_tokens": 80,
                "temperature": 0.1,
                "messages": [{"role": "user", "content": prompt}],
            },
        }))

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write("\n".join(lines))
        tmp_path = f.name

    try:
        with open(tmp_path, "rb") as f:
            uploaded = client.files.create(file=f, purpose="batch")
        batch = client.batches.create(
            input_file_id=uploaded.id,
            endpoint="/v1/chat/completions",
            completion_window="24h",
        )
        return batch.id
    finally:
        import os as _os
        _os.unlink(tmp_path)


def poll_batch(batch_id: str, provider: str | None = None) -> dict | None:
    """Check batch status. Returns {status, results} or None.
    Provider param overrides global PROVIDER (for polling historical batches).
    """
    prov = (provider or PROVIDER).lower()
    if prov == "anthropic":
        return _poll_anthropic_batch(batch_id)
    if prov == "openai":
        return _poll_openai_batch(batch_id)
    if prov == "ollama":
        return _poll_ollama_batch(batch_id)
    return None


def _poll_ollama_batch(batch_id: str) -> dict | None:
    """
    Ollama batches are run synchronously in _create_ollama_batch().
    The results are embedded directly in the batch_id string as:
      'LOCAL_BATCH_DONE:{json_array}'
    So polling is instant — just parse the embedded results.
    """
    if batch_id.startswith("LOCAL_BATCH_DONE:"):
        try:
            results_json = batch_id[len("LOCAL_BATCH_DONE:"):]
            results = json.loads(results_json)
            return {"status": "completed", "results": results}
        except Exception as e:
            print(f"[poll_ollama_batch] failed to parse embedded results: {e}")
            return {"status": "completed", "results": []}
    # Shouldn't happen, but treat unknown IDs as still in progress
    return {"status": "in_progress", "results": []}



def _poll_anthropic_batch(batch_id):
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


def _poll_openai_batch(batch_id):
    """Poll OpenAI batch: retrieve status → download output JSONL → parse results."""
    from openai import OpenAI
    client = OpenAI(api_key=API_KEY)
    batch = client.batches.retrieve(batch_id)

    if batch.status in ("validating", "in_progress", "finalizing"):
        return {"status": "in_progress", "results": []}
    if batch.status in ("failed", "expired", "cancelled"):
        return {"status": batch.status, "results": []}

    # completed — download output
    if not batch.output_file_id:
        return {"status": "completed", "results": []}

    content = client.files.content(batch.output_file_id).text
    results = []
    for line in content.strip().split("\n"):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            custom_id = entry.get("custom_id", "")
            score, reason = 0, ""
            body = entry.get("response", {}).get("body", {})
            choices = body.get("choices", [])
            if choices:
                raw_text = choices[0].get("message", {}).get("content", "").strip()
                raw_text = re.sub(r"^```[a-z]*\n?", "", raw_text)
                raw_text = re.sub(r"\n?```$", "", raw_text).strip()
                try:
                    data = json.loads(raw_text)
                    score = int(data.get("score", 0))
                    reason = str(data.get("reason", ""))[:120]
                except Exception:
                    reason = "parse error"
            results.append({"custom_id": custom_id, "score": score, "reason": reason})
        except json.JSONDecodeError:
            continue
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
