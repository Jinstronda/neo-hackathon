"""The loop's promises, offline: the fixer loops back until verify() proves the
patch, a human approval gates blue, and OFFLINE_ASK drives a whole run to
merge_ready with no model call. Mock red agent, local PR records, process twins
(Docker is switched off), a staged radar match, and no gateway key, so no real
model call can succeed.

These tests run the loop, and the loop runs pytest (gate.run_tests). They skip
inside that nested run, so the gate never re-runs the loop that called it."""
import functools
import json
import os

import _patch
import pytest

from neo import factory, gate, llm, orchestrator

pytestmark = pytest.mark.skipif(
    bool(os.environ.get(gate.NESTED_ENV)),
    reason="inside the gate's own pytest run: the loop does not re-run itself")

MODELS = ["model-a"]  # the mock agent runs one reference chain per scenario
RADAR = {"sbom_size": 1, "kev_source": "staged-only", "matches": [{
    "package": "PyYAML", "version": "5.3.1", "ecosystem": "PyPI", "cve": "CVE-2020-14343",
    "osv": ["GHSA-8q59-q68h-6hv4"], "summary": "staged", "kev": True, "epss": 0.5,
    "reachable": True}]}


def _no_docker(*_a, **_k):
    raise RuntimeError("Docker is off in tests")


@pytest.fixture
def runs(monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(orchestrator.radar, "scan", lambda: RADAR)
    monkeypatch.setattr(gate.replay, "replay", _no_docker)
    monkeypatch.setattr(factory, "open_pr",
                        functools.partial(factory.open_pr, store=tmp_path / "prs"))
    monkeypatch.setenv(llm.config.API_KEY_ENV, "")
    monkeypatch.setattr(llm, "USAGE", [])
    return tmp_path / "runs"


def _events(runs, run_id):
    return [json.loads(ln) for ln in (runs / run_id / "events.jsonl").read_text().splitlines()]


def _of(events, kind):
    return [e for e in events if e["type"] == kind]


def _edit(label, before, after):
    return {"finding_id": label.split()[0], "before": before, "after": after}


def _loop(run_id, **kw):
    return orchestrator.loop(run_id, repo=None, models=MODELS, screenshots=False,
                             agent="mock", **kw)


def test_fixer_loops_back_until_verify_proves_the_patch(runs, monkeypatch):
    monkeypatch.setattr(gate, "run_tests", lambda journal=None, **_: (True, 1, 1))
    sqli_only = [_edit(*f) for f in _patch.FIXES if f[0].startswith("A")]
    proposals = [sqli_only, [_edit(*f) for f in _patch.FIXES]]
    fixer_calls = []

    def ask(model, messages, *, description, **_):
        if "fixer" not in description:
            return orchestrator.OFFLINE_ASK(model, messages, description=description)
        fixer_calls.append(messages)
        return {"fixes": proposals[len(fixer_calls) - 1]}

    s = _loop("t-loopback", ask=ask)
    events = _events(runs, "t-loopback")
    attempts = _of(events, "fix_attempt")
    assert [(a["attempt"], a["source"], a["ok"]) for a in attempts] == [
        (1, "model", False), (2, "model", True)]
    assert attempts[0]["exploits_dead"] == {
        "sql-injection": True, "ssrf-metadata": False, "weak-jwt-secret": False}
    assert attempts[1]["legit_login_ok"] is True
    # the second ask carries exactly what still landed
    feedback = fixer_calls[1][-1]["content"]
    assert "ssrf-metadata, weak-jwt-secret" in feedback and "sql-injection" not in feedback
    # only the verified patch is opened, after the attempt that proved it
    kinds = [e["type"] for e in events]
    assert kinds.count("blue_patch") == 1
    assert kinds.index("blue_patch") > events.index(attempts[1])
    assert s["pr"]["patch_source"] == "model" and s["merge"]["ready"] is True


def test_declined_approval_stops_before_blue(runs):
    asked = []
    s = _loop("t-declined", ask=orchestrator.OFFLINE_ASK,
              approve=lambda findings: asked.append(findings) or False)
    assert len(asked) == 1 and len(asked[0]) == 3
    events = _events(runs, "t-declined")
    assert not _of(events, "blue_patch") and not _of(events, "fix_attempt")
    assert [(e["approved"], e["by"]) for e in _of(events, "fix_approval")] == [(False, "human")]
    on_disk = json.loads((runs / "t-declined" / "run.json").read_text())
    assert s["merge"]["awaiting"] == on_disk["merge"]["awaiting"] == "fix approval"
    assert s["pr"] is None and s["merge"]["ready"] is False


def test_remediate_refuses_a_declined_fix(runs):
    ctx = orchestrator.start("t-refuse", models=MODELS, live=False, agent="mock")
    ctx["findings"] = [{"finding_id": "A1"}]
    orchestrator.record_approval(ctx, False)
    with pytest.raises(PermissionError):
        orchestrator.remediate(ctx)


def test_offline_ask_runs_end_to_end_with_no_model_call(runs, monkeypatch):
    s = _loop("t-offline", ask=orchestrator.OFFLINE_ASK)
    assert llm.USAGE == []
    events = _events(runs, "t-offline")
    assert [(e["approved"], e["by"]) for e in _of(events, "fix_approval")] == [(True, "auto")]
    assert [(a["source"], a["ok"]) for a in _of(events, "fix_attempt")] == [
        ("model", False), ("canonical", True)]
    assert [r["ready"] for r in _of(events, "merge_ready")] == [True]
    # the real suite ran nested (this file skipped there) and passed
    (tests,) = _of(events, "tests")
    assert tests["ok"] is True and tests["passed"] >= 7
    assert s["retest"]["post_patch_green"] is True and s["review"]["offline"] is True
    assert json.loads((runs / "t-offline" / "run.json").read_text())["merge"]["ready"] is True
    # the evidence panels render from the summary alone
    panels = []
    monkeypatch.setattr(orchestrator.shots, "panel", lambda name, *_: panels.append(name))
    orchestrator._screens(s, s["review"]["verdicts"])
    assert panels == ["01-radar", "02-red-prepatch", "04-review", "05-green-postpatch",
                      "06-merge-ready"]


def test_run_id_cannot_escape_runs(runs):
    for bad in ("../x", "", "a/b", ".hidden"):
        with pytest.raises(ValueError):
            orchestrator.start(bad, live=False, agent="mock")
