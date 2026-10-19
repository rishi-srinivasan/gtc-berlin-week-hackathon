"""Baseline redactor: a frontier LLM extracts German PII, every call traced in Langfuse."""
import os

from dotenv import load_dotenv

load_dotenv()

from . import ollama  # noqa: E402
from .schema import SYSTEM_PROMPT  # noqa: E402
from .trace import batch_args, run_batch, traced_extract  # noqa: E402


def make_call():
    """Return (model, provider, call) for TEACHER_PROVIDER = ollama (default) | anthropic | openai."""
    provider = os.getenv("TEACHER_PROVIDER", "ollama")
    if provider == "ollama":
        model = os.getenv("TEACHER_MODEL", "gemma4:12b")
        return model, provider, lambda text: ollama.chat(
            model, [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}])
    if provider == "anthropic":
        import anthropic
        client, model = anthropic.Anthropic(), os.getenv("TEACHER_MODEL", "claude-sonnet-5-5")

        def call(text):
            r = client.messages.create(model=model, max_tokens=2000, system=SYSTEM_PROMPT,
                                       messages=[{"role": "user", "content": text}])
            return r.content[0].text, r.usage.input_tokens, r.usage.output_tokens
        return model, provider, call
    if provider == "openai":
        import openai
        client, model = openai.OpenAI(), os.getenv("TEACHER_MODEL", "gpt-5-mini")

        def call(text):
            r = client.chat.completions.create(
                model=model, response_format={"type": "json_object"},
                messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}])
            return r.choices[0].message.content, r.usage.prompt_tokens, r.usage.completion_tokens
        return model, provider, call
    raise SystemExit(f"TEACHER_PROVIDER must be ollama|anthropic|openai, got {provider!r}")


def tags(provider: str, model: str) -> list[str]:
    return ["teacher", "baseline", f"provider:{provider}", f"model:{model}"]


def redact_entities(text: str, uid=None, split: str = "") -> dict:
    model, provider, call = make_call()
    return traced_extract("teacher", text, call, model=model, tags=tags(provider, model),
                          uid=uid, split=split)


def main():
    a = batch_args(__doc__)
    model, provider, call = make_call()
    print("->", run_batch("teacher", call, model=model, tags=tags(provider, model),
                          split=a.split, n=a.n, data=a.data))


if __name__ == "__main__":
    main()
