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
RUNNER = pathlib.Path(__file__).resolve().parents[3] / "neo-web" / "ops" / "cloud_runner.py"
spec = importlib.util.spec_from_file_location("cloud_runner", RUNNER)
cr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cr)

PRE_TRUE = {"type": "flag_check", "phase": "pre-patch", "objective_complete": True}
PRE_FALSE = {"type": "flag_check", "phase": "pre-patch", "objective_complete": False}
GREEN = {"type": "retest", "status": "green", "objective_complete": False}
REVS = [{"type": "review", "reviewer": "security", "verdict": "approve"},
        {"type": "review", "reviewer": "correctness", "verdict": "approve"}]


def test_merge_gate():
    # forged approval: exploit never proven -> merge refused even with green + two approvals
    ok, _ = cr.merge_ready([PRE_FALSE, GREEN] + REVS)
    assert ok is False, "merge allowed without a proven exploit (forged approval)"
    # only one approver
    ok, _ = cr.merge_ready([PRE_TRUE, GREEN, REVS[0]])
    assert ok is False, "merge allowed with a single reviewer"
    # retest not green
    ok, _ = cr.merge_ready([PRE_TRUE, {"type": "retest", "status": "red", "objective_complete": True}] + REVS)
    assert ok is False, "merge allowed with the exploit still alive"
    # the honest path: proven + green + two approvals
    ok, approvers = cr.merge_ready([PRE_TRUE, GREEN] + REVS)
    assert ok is True and sorted(approvers) == ["correctness", "security"], "the legitimate merge was refused"
    # already merged -> refused
    ok, _ = cr.merge_ready([PRE_TRUE, GREEN] + REVS + [{"type": "merge"}])
    assert ok is False, "a second merge was allowed"


def test_scrub():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJ1IjoiYWRtaW4ifQ.c2lnbmF0dXJlLWhlcmU"
    box = os.environ["NEO_EVE_SECRET"]
    event = {
        "type": "blue_patch",
        "diff": 'WEAK_JWT_SECRET = "neo-demo-secret"\nAuthorization: Bearer ' + jwt,
        "request": "GET /u?token=" + jwt,
        "evidence": ["cookie: session=abc123deadbeef", "plain evidence line"],
        "note": "box secret is " + box,
        "location": "GET /api/render?template=",  # must survive untouched
    }
    out = cr.scrub(event)
    blob = str(out)
    assert jwt not in blob, "JWT leaked"
    assert "neo-demo-secret" not in blob, "weak secret value leaked from the diff"
    assert box not in blob, "the box secret leaked"
    assert "abc123deadbeef" not in blob, "cookie value leaked"
    assert out["location"] == "GET /api/render?template=", "scrub damaged a non-secret field"
    assert out["type"] == "blue_patch" and "plain evidence line" in blob, "scrub dropped legitimate content"


if __name__ == "__main__":
    test_merge_gate()
    test_scrub()
    print("PASS  merge-gate (no forged approval)")
    print("PASS  event-scrub (no secret leaves the box)")
