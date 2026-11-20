"""The LLM boundary. Every model call in NEO goes through here, never a
provider SDK. OpenAI-compatible calls to the HomoDeus LLM gateway."""
import json
import os
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


def chat(model, messages, *, description, temperature=0.2, timeout=120, tools=None):
    """One completion. Returns the assistant message content (str)."""
    body = {"model": model, "messages": messages, "temperature": temperature}
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(
        f"{config.GATEWAY_BASE}/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {_key()}",
            "Content-Type": "application/json",
            "X-HomoDeus-Project": config.PROJECT_HEADER,
            "X-HomoDeus-Description": description,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise LLMError(f"gateway {e.code}: {e.read()[:400]!r}") from e
    USAGE.append({"model": model, "served": data.get("model"),
                  "usage": data.get("usage") or {}})
    return data["choices"][0]["message"]["content"] or ""


def chat_json(model, messages, *, description, timeout=120):
    """Completion that must return a JSON object. Retries once on parse fail."""
    for attempt in range(2):
        out = chat(model, messages, description=description, timeout=timeout)
        txt = out.strip()
        if txt.startswith("```"):
            txt = txt.split("```", 2)[1].lstrip("json").strip()
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            if attempt == 0:
                messages = messages + [{"role": "user", "content": "Return only valid JSON, no prose."}]
                continue
            raise LLMError(f"model did not return JSON: {out[:300]!r}")
