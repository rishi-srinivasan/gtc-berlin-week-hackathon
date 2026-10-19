"""Client for the served small model (OpenAI-compatible, e.g. vLLM on Runpod). Same prompt/schema as the teacher."""
import os

from dotenv import load_dotenv

load_dotenv()

import openai  # noqa: E402

from . import ollama  # noqa: E402
from .schema import SYSTEM_PROMPT  # noqa: E402
from .trace import batch_args, run_batch, traced_extract  # noqa: E402


def make_call():
    """Return (model, version, provider, call) for STUDENT_PROVIDER = ollama (default) | runpod.

    ollama: STUDENT_MODEL defaults to the untuned qwen3:1.7b; set it to pii-student for the distil GGUF.
    runpod: needs STUDENT_BASE_URL and STUDENT_MODEL (vLLM, OpenAI-compatible).
    """
    provider = os.getenv("STUDENT_PROVIDER", "ollama")
    version = os.getenv("STUDENT_VERSION", "v0")
    msgs = lambda text: [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}]  # noqa: E731
    if provider == "ollama":
        model = os.getenv("STUDENT_MODEL", "qwen3:1.7b")
        return model, version, provider, lambda text: ollama.chat(model, msgs(text))
    if provider == "runpod":
        base, model = os.getenv("STUDENT_BASE_URL"), os.getenv("STUDENT_MODEL")
        if not (base and model):
            raise SystemExit("Set STUDENT_BASE_URL and STUDENT_MODEL in .env (see scripts/runpod_serve.md).")
        client = openai.OpenAI(base_url=base, api_key=os.getenv("STUDENT_API_KEY", "EMPTY"))

        def call(text):
            r = client.chat.completions.create(model=model, temperature=0, messages=msgs(text))
            return r.choices[0].message.content, r.usage.prompt_tokens, r.usage.completion_tokens
        return model, version, provider, call
    raise SystemExit(f"STUDENT_PROVIDER must be ollama|runpod, got {provider!r}")


def tags(provider: str, model: str, version: str) -> list[str]:
    return ["student", f"provider:{provider}", f"model:{model}", f"version:{version}"]


def redact_entities(text: str, uid=None, split: str = "") -> dict:
    model, version, provider, call = make_call()
    return traced_extract("student", text, call, model=model, tags=tags(provider, model, version),
                          uid=uid, split=split, version=version)


if __name__ == "__main__":
    a = batch_args(__doc__)
    model, version, provider, call = make_call()
    print("->", run_batch("student", call, model=model, tags=tags(provider, model, version),
                          version=version, split=a.split, n=a.n, data=a.data))
