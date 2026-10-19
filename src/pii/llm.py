"""One chat function per role (TEACHER, STUDENT, FRONTIER), configured only through env vars:

  {ROLE}_PROVIDER  openai (default: any OpenAI-compatible API — OpenAI, vLLM on Runpod, distil endpoint, Ollama)
                   | anthropic
  {ROLE}_MODEL     model name (required)
  {ROLE}_BASE_URL  OpenAI-compatible endpoint; empty = api.openai.com
  {ROLE}_API_KEY   empty = OPENAI_API_KEY / ANTHROPIC_API_KEY
  {ROLE}_EXTRA     JSON of extra request params, e.g. {"temperature": 0, "reasoning_effort": "none"}
"""
import json
import os


def make_chat(role: str):
    """Return (model, chat) where chat(messages, schema=None) -> (reply, tokens_in, tokens_out)."""
    get = lambda key, default=None: os.getenv(f"{role}_{key}") or default  # noqa: E731
    model = get("MODEL")
    if not model:
        raise SystemExit(f"Set {role}_MODEL in .env (see README).")
    extra = json.loads(get("EXTRA", "{}"))
    if get("PROVIDER", "openai") == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=get("API_KEY"))

        def chat(messages, schema=None):  # Anthropic has no JSON-schema mode; the prompt asks for JSON
            r = client.messages.create(model=model, max_tokens=2000, system=messages[0]["content"],
                                       messages=messages[1:], **extra)
            return r.content[0].text, r.usage.input_tokens, r.usage.output_tokens
        return model, chat

    import openai
    client = openai.OpenAI(base_url=get("BASE_URL"), api_key=get("API_KEY", os.getenv("OPENAI_API_KEY", "EMPTY")))

    def chat(messages, schema=None):
        fmt = {"response_format": {"type": "json_schema", "json_schema": {"name": "entities", "schema": schema}}} if schema else {}
        r = client.chat.completions.create(model=model, messages=messages, **fmt, extra_body=extra)  # extra_body passes server-specific keys too
        return r.choices[0].message.content, r.usage.prompt_tokens, r.usage.completion_tokens
    return model, chat
