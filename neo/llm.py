"""The LLM boundary. Every model call in NEO goes through here, never a
provider SDK. OpenAI-compatible calls to the HomoDeus LLM gateway, with retries
on transient gateway failures so one 429 or dropped socket never fails a run."""
import json
import os
import time
import urllib.error
import urllib.request

from . import config


class LLMError(RuntimeError):
    pass


# Token + cost accounting (a boundary responsibility). One record per completion.
USAGE = []
# USD per 1M tokens (prompt, completion), gateway rates read 2026-11-20.
_PRICE = {
    "gemini-3.8-flash": (0.75, 3.75),
    "gpt-6-luna": (0.10, 0.50),
    "gpt-6.2-sol": (0.10, 0.50),
}
_DEFAULT_PRICE = (0.75, 3.75)

# Retry transient gateway failures with exponential backoff. 429 and 5xx are the
# gateway telling us to come back; a dropped socket (URLError) is the network.
_RETRY_STATUS = {429, 500, 502, 503, 504}
_MAX_TRIES = 4
_BACKOFF_BASE = 0.5


def usage_summary():
    pt = sum(u["usage"].get("prompt_tokens", 0) for u in USAGE)
    ct = sum(u["usage"].get("completion_tokens", 0) for u in USAGE)
    usd = 0.0
    for u in USAGE:
        pin, pout = _PRICE.get(u.get("served") or "", _DEFAULT_PRICE)
        usd += (u["usage"].get("prompt_tokens", 0) / 1e6 * pin
                + u["usage"].get("completion_tokens", 0) / 1e6 * pout)
    return {"calls": len(USAGE), "prompt_tokens": pt, "completion_tokens": ct,
            "est_usd": round(usd, 4),
            "priced_as": "served-model gateway rates (2026-11-20), estimate"}


def _key():
    k = os.environ.get(config.API_KEY_ENV)
    if not k:
        raise LLMError(f"{config.API_KEY_ENV} not set; load .env")
    return k


def _completion(model, messages, *, description, temperature, timeout, tools):
    """One gateway completion with retries. Returns the assistant message dict.
    Never sets max_tokens: a cap draws from the reasoning budget."""
    body = {"model": model, "messages": messages, "temperature": temperature}
    if tools:
        body["tools"] = tools
    data = json.dumps(body).encode()
    headers = {
        "Authorization": f"Bearer {_key()}",
        "Content-Type": "application/json",
        "X-HomoDeus-Project": config.PROJECT_HEADER,
        "X-HomoDeus-Description": description,
    }
    parsed = None
    for attempt in range(_MAX_TRIES):
        req = urllib.request.Request(f"{config.GATEWAY_BASE}/chat/completions",
                                     data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                parsed = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code not in _RETRY_STATUS or attempt == _MAX_TRIES - 1:
                raise LLMError(f"gateway {e.code}: {e.read()[:400]!r}") from e
        except urllib.error.URLError as e:
            if attempt == _MAX_TRIES - 1:
                raise LLMError(f"gateway unreachable: {e.reason}") from e
        time.sleep(_BACKOFF_BASE * 2 ** attempt)
    USAGE.append({"model": model, "served": parsed.get("model"),
                  "usage": parsed.get("usage") or {}})
    return parsed["choices"][0]["message"]


def chat(model, messages, *, description, temperature=0.2, timeout=120, tools=None):
    """One completion. Returns the assistant message content (str)."""
    msg = _completion(model, messages, description=description,
                      temperature=temperature, timeout=timeout, tools=tools)
    return msg.get("content") or ""


def chat_message(model, messages, *, description, tools=None, temperature=0.2, timeout=120):
    """One completion, returning the full assistant message: its `content` and any
    `tool_calls` (OpenAI-compatible). The agentic chat loop reads both."""
    return _completion(model, messages, description=description,
                       temperature=temperature, timeout=timeout, tools=tools)


def chat_json(model, messages, *, description, timeout=120):
    """Completion that must return a JSON object. Retries once on parse fail."""
    for attempt in range(2):
        out = chat(model, messages, description=description, timeout=timeout)
        txt = out.strip()
        if txt.startswith("```"):
            txt = txt.split("```", 2)[1].lstrip("json").strip()
        try:
            return json.loads(txt)
        except json.JSONDecodeError as e:
            if attempt == 0:
                messages = messages + [{"role": "user",
                                        "content": "Return only valid JSON, no prose."}]
                continue
            raise LLMError(f"model did not return JSON: {out[:300]!r}") from e
