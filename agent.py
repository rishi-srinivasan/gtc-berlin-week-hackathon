"""Intent-routing demo agent, traced with Langfuse.

Swap the model via .env: any OpenAI-compatible endpoint works (OpenAI, or a
distilled model served with vLLM on Runpod) -- traces stay comparable.
"""
import json
import os
import re
import uuid

from dotenv import load_dotenv

load_dotenv()  # before importing langfuse so it sees the credentials

from langfuse import Langfuse, get_client, observe, propagate_attributes  # noqa: E402
from langfuse.openai import OpenAI  # noqa: E402  (drop-in client: auto generation, model, tokens)

INTENTS = ["billing", "tech_support", "account", "cancellation", "other"]
MODEL = os.getenv("LLM_MODEL", "gpt-5-mini")


def mask(data, **_):
    """Scrub emails / long digit runs from everything sent to Langfuse."""
    if isinstance(data, str):
        data = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "<email>", data)
        return re.sub(r"\b\d[\d -]{7,}\d\b", "<number>", data)
    if isinstance(data, dict):
        return {k: mask(v) for k, v in data.items()}
    if isinstance(data, list):
        return [mask(v) for v in data]
    return data


Langfuse(mask=mask)  # registers the global client used by get_client()
llm = OpenAI(base_url=os.getenv("LLM_BASE_URL"), api_key=os.getenv("LLM_API_KEY"))

ROUTE_TOOL = {
    "type": "function",
    "function": {
        "name": "route",
        "description": "Route the customer message to the right team.",
        "parameters": {
            "type": "object",
            "properties": {"intent": {"type": "string", "enum": INTENTS}},
            "required": ["intent"],
        },
    },
}


@observe(name="classify-intent", as_type="agent", capture_input=False)
def classify(message: str) -> str:
    get_client().update_current_span(input=message)
    resp = llm.chat.completions.create(
        name="route-llm-call",
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a support triage router. Always call `route`."},
            {"role": "user", "content": message},
        ],
        tools=[ROUTE_TOOL],
        tool_choice={"type": "function", "function": {"name": "route"}},
    )
    calls = resp.choices[0].message.tool_calls
    intent = json.loads(calls[0].function.arguments)["intent"] if calls else "other"
    return intent if intent in INTENTS else "other"


@observe(name="queue-handoff", as_type="tool", capture_input=False)
def handoff(intent: str) -> str:
    get_client().update_current_span(input={"intent": intent})
    return f"ticket-{uuid.uuid4().hex[:8]} -> {intent}-queue"  # stand-in for a real ticketing call


@observe(name="support-routing", capture_input=False)
def route_message(message: str, session_id: str) -> dict:
    lf = get_client()
    with propagate_attributes(session_id=session_id, tags=["feature:intent-routing"],
                              metadata={"model": MODEL}):
        lf.update_current_span(input=message)  # only the user message, not session/config args
        intent = classify(message)
        ticket = handoff(intent)
        result = {"intent": intent, "ticket": ticket}
        lf.update_current_span(output=result)
        return result


if __name__ == "__main__":
    samples = [
        "I was charged twice this month, my card ends 4242 4242 4242 4242",
        "The app crashes whenever I upload a photo",
        "Please change my login email to jane.doe@example.com",
        "I want to cancel my subscription",
    ]
    sid = f"demo-{uuid.uuid4().hex[:6]}"
    for m in samples:
        print(route_message(m, sid))
    get_client().flush()  # short-lived script: send traces before exit
    print("session:", sid)
