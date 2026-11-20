#!/usr/bin/env python3
"""Checks the two runner security fixes in neo-web/ops/cloud_runner.py:
the merge gate (no forged approval) and event scrubbing (no secret leaves the box).

Run: NEO_EVE_SECRET=box-secret-xyz python3 qa/contract/test_cloud_runner.py
Stdlib only; loads the runner module by path so it works from either repo.
"""
import importlib.util
import os
import pathlib
import sys

os.environ.setdefault("NEO_EVE_SECRET", "box-secret-xyz-123")
RUNNER = pathlib.Path(__file__).resolve().parents[2] / "console" / "ops" / "cloud_runner.py"
spec = importlib.util.spec_from_file_location("cloud_runner", RUNNER)
cr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cr)

PRE_TRUE = {"type": "flag_check", "phase": "pre-patch", "objective_complete": True}
PRE_FALSE = {"type": "flag_check", "phase": "pre-patch", "objective_complete": False}
GREEN = {"type": "retest", "status": "green", "objective_complete": False}
APPROVE = [{"type": "review", "reviewer": "security", "verdict": "approve"},
           {"type": "review", "reviewer": "correctness", "verdict": "approve"}]


def test_merge_gate():
    # forged approval: exploit never proven -> refused even with green + both approvals
    assert cr.merge_ready([PRE_FALSE, GREEN] + APPROVE)[0] is False, "merge allowed without a proven exploit"
    # two approvals from the same reviewer must not count as the required set
    assert cr.merge_ready([PRE_TRUE, GREEN, APPROVE[0], dict(APPROVE[0])])[0] is False, "duplicate reviewer counted twice"
    # a request_changes on this attempt blocks the merge
    assert cr.merge_ready([PRE_TRUE, GREEN] + APPROVE + [{"type": "review", "reviewer": "security", "verdict": "request_changes"}])[0] is False, "request_changes ignored"
    # exploit still alive after the patch -> refused
    assert cr.merge_ready([PRE_TRUE, {"type": "retest", "status": "red", "objective_complete": True}] + APPROVE)[0] is False, "merge with a live exploit"
    # the honest path
    ok, approvers = cr.merge_ready([PRE_TRUE, GREEN] + APPROVE)
    assert ok is True and approvers == ["correctness", "security"], "the legitimate merge was refused"
    # no second merge
    assert cr.merge_ready([PRE_TRUE, GREEN] + APPROVE + [{"type": "merge"}])[0] is False, "a second merge was allowed"


def test_scrub():
    import base64
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJ1IjoiYWRtaW4ifQ.c2lnbmF0dXJlLWhlcmU"
    box = os.environ["NEO_EVE_SECRET"]
    enc = base64.b64encode(box.encode()).decode()
    response = cr.scrub({
        "run": {"metrics": {"cost_usd": 1}},
        "events": [
            {"type": "blue_patch", "diff": 'WEAK_JWT_SECRET = "neo-demo-secret"\nAuthorization: Bearer ' + jwt},
            {"type": "red_finding", "request": "Cookie: a=1; sid=deadbeefsecret; b=2", "response": "tok " + jwt,
             "location": "GET /api/render?template="},
            {"type": "note", "authorization": "Bearer abc", "blob": "env " + box + " b64 " + enc},
        ],
        "source": "engine",
    })
    blob = str(response)
    for bad, label in [(jwt, "JWT"), ("neo-demo-secret", "weak secret from diff"), ("deadbeefsecret", "cookie value"),
                       (box, "env secret"), (enc, "base64 of env secret"), ("Bearer abc", "value under a secret key")]:
        assert bad not in blob, f"leaked: {label}"
    assert response["events"][1]["location"] == "GET /api/render?template=", "scrub damaged a non-secret field"


def test_gen_isolation():
    cr.state["gen"] = 5
    cr.state["live"] = []
    cr.emit({"type": "merge"}, gen=4)   # a late emit from a previous run
    assert cr.state["live"] == [], "stale-generation emit was not dropped"
    cr.emit({"type": "merge"}, gen=5)
    assert len(cr.state["live"]) == 1, "current-generation emit was dropped"


def test_fix_crash_releases_lock():
    # a crash inside fix() must clear state["fixing"], or no further attack is ever accepted
    cr.state["gen"] = 7
    cr.state["fixing"] = True
    cr.fix = _boom  # type: ignore  # force a failure in the blue phase
    try:
        cr.run_fix(7)
    finally:
        cr.fix = _real_fix  # type: ignore
    assert cr.state["fixing"] is False, "a crashed fix left the runner wedged (DoS)"


if __name__ == "__main__":
    _real_fix = cr.fix

    def _boom(_gen):
        raise RuntimeError("blue phase blew up")

    test_merge_gate()
    test_scrub()
    test_gen_isolation()
    test_fix_crash_releases_lock()
    print("PASS  merge-gate (no forged approval, exact reviewer set, no request_changes)")
    print("PASS  event-scrub (jwt, diff secret, cookie, env secret + base64, secret-keyed fields)")
    print("PASS  gen-isolation (stale-run events cannot reach the gate)")
    print("PASS  fix-crash releases the lock (no DoS wedge)")
