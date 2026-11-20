"""The terminal agent: the human merge gate is in the REPL, not the prompt, so a
fix runs only when the human types yes. Tools reject unknown names and skill
path traversal. The orchestrator is faked so the test does not run the real loop."""
import io

from neo import chat, orchestrator, tools


def _fake_orchestrator(monkeypatch):
    calls = {"remediate": 0}

    def start(run_id, *, models=None, live=True, agent="swarm", ask=None):
        return {"id": run_id, "agent": agent, "dir": None}

    def attack(ctx):
        return [{"cls": "sql-injection", "location": "POST /login",
                 "confirmed_by": "server-side flag check", "found_by": ["model-1"]}]

    def remediate(ctx, *, repo=None, screenshots=False, max_fix_attempts=3):
        calls["remediate"] += 1
        return {"pr": {"url": "runs/x/PR.json", "number": 0, "mode": "local"},
                "review": {"verdicts": [{"reviewer": "security", "vendor": "OpenAI",
                                         "verdict": "approve"}]},
                "retest": {"post_patch_green": True, "tests": "11/11"},
                "merge": {"ready": True, "awaiting": "human"}}

    monkeypatch.setattr(orchestrator, "start", start, raising=False)
    monkeypatch.setattr(orchestrator, "attack", attack, raising=False)
    monkeypatch.setattr(orchestrator, "remediate", remediate, raising=False)
    return calls


def _reader(lines):
    it = iter(lines)

    def read(prompt):
        try:
            return next(it)
        except StopIteration:
            return None

    return read


def _run(monkeypatch, lines):
    calls = _fake_orchestrator(monkeypatch)
    out = io.StringIO()
    session = tools.Session(agent="mock", ask=None)
    messages = [{"role": "system", "content": "sys"}]
    chat.run_repl(chat.mock_model, session, messages, reader=_reader(lines), out=out)
    return calls, session, out.getvalue()


def test_fix_runs_only_on_yes(monkeypatch):
    calls, session, text = _run(monkeypatch, ["attack our server", "fix it", "y"])
    assert calls["remediate"] == 1
    assert session.summary is not None
    assert "ready for a human to merge" in text


def test_fix_refused_on_no(monkeypatch):
    calls, session, text = _run(monkeypatch, ["attack our server", "fix it", "n"])
    assert calls["remediate"] == 0
    assert session.summary is None
    assert "not touch it" in text


def test_unknown_tool_is_data_not_exception():
    session = tools.Session(agent="mock")
    res = tools.call(session, "no_such_tool", {})
    assert "error" in res


def test_fix_before_attack_errors():
    session = tools.Session(agent="mock")
    res = tools.fix(session)
    assert "error" in res and "attack" in res["error"].lower()


def test_read_skill_rejects_traversal():
    session = tools.Session(agent="mock")
    assert "error" in tools.call(session, "read_skill", {"name": "../x"})
    assert "error" in tools.call(session, "read_skill", {"name": "a/b"})
    ok = tools.call(session, "read_skill", {"name": "breachbench"})
    assert "content" in ok and "breachbench" in ok["content"]
