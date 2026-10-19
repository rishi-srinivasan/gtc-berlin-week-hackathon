"""Local Ollama chat via the native /api/chat (needed for `format`, `think` and `num_ctx`, which the
OpenAI-compatible /v1 endpoint does not accept)."""
import os

import httpx

from .schema import OUTPUT_SCHEMA


def host() -> str:
    return os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")


def chat(model: str, messages: list[dict], schema: dict | None = OUTPUT_SCHEMA) -> tuple[str, int, int]:
    """Return (reply, prompt_tokens, completion_tokens). schema=None gives free text."""
    body = {"model": model, "messages": messages, "stream": False, "think": False,
            "options": {"temperature": 0, "num_ctx": 4096}}
    if schema:
        body["format"] = schema  # constrained decoding to the entity JSON schema
    r = httpx.post(f"{host()}/api/chat", json=body, timeout=300)
    r.raise_for_status()
    d = r.json()
    return d["message"]["content"], d.get("prompt_eval_count", 0), d.get("eval_count", 0)
