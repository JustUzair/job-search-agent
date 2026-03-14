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
