"""The LLM boundary: retries on transient gateway failures, surfaces tool_calls,
and never sends a token cap. Patches urllib, so nothing touches the network."""
import io
import json
import urllib.error

import pytest

from neo import llm


class _Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_error(code):
    return urllib.error.HTTPError("https://gw/x", code, "err", {}, io.BytesIO(b"body"))


def _ok(message=None):
    return {"model": "served-m", "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            "choices": [{"message": message or {"content": "ok"}}]}


def _patch(monkeypatch, outcomes, captured):
    it = iter(outcomes)

    def urlopen(req, timeout=None):
        captured.append(json.loads(req.data.decode()))
        outcome = next(it)
        if isinstance(outcome, Exception):
            raise outcome
        return _Resp(outcome)

    monkeypatch.setenv("HOMODEUS_API_KEY", "test-key")
    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(llm.time, "sleep", lambda *_: None)


def test_retries_on_429_then_succeeds(monkeypatch):
    captured = []
    _patch(monkeypatch, [_http_error(429), _ok()], captured)
    out = llm.chat("m", [{"role": "user", "content": "hi"}], description="t")
    assert out == "ok"
    assert len(captured) == 2  # one retry after the 429


def test_no_retry_on_400(monkeypatch):
    captured = []
    _patch(monkeypatch, [_http_error(400)], captured)
    with pytest.raises(llm.LLMError):
        llm.chat("m", [{"role": "user", "content": "hi"}], description="t")
    assert len(captured) == 1  # a client error is not retried


def test_retries_on_network_error(monkeypatch):
    captured = []
    _patch(monkeypatch, [urllib.error.URLError("reset"), _ok()], captured)
    assert llm.chat("m", [{"role": "user", "content": "hi"}], description="t") == "ok"
    assert len(captured) == 2


def test_tool_calls_surfaced(monkeypatch):
    captured = []
    msg = {"role": "assistant", "content": None,
           "tool_calls": [{"id": "c1", "type": "function",
                           "function": {"name": "attack", "arguments": "{}"}}]}
    _patch(monkeypatch, [_ok(msg)], captured)
    out = llm.chat_message("m", [{"role": "user", "content": "go"}], description="t",
                           tools=[{"type": "function", "function": {"name": "attack"}}])
    assert out["tool_calls"][0]["function"]["name"] == "attack"
    assert "tools" in captured[0]


def test_no_token_cap_in_body(monkeypatch):
    captured = []
    _patch(monkeypatch, [_ok()], captured)
    llm.chat("m", [{"role": "user", "content": "hi"}], description="t")
    body = captured[0]
    assert "max_tokens" not in body
    assert "max_completion_tokens" not in body
    assert "maxTokens" not in body
