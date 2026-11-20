"""The retest + merge gate. Rebuild a fresh twin from the patched code, replay the
same exploits, and read the verdict from the twin's own server-side event log
(infra.replay is the core, not reimplemented here). Then run the tests. The PR is
ready to merge only when the exploit is proven dead server-side AND the tests pass
AND both reviewers approve the exact diff. This module never merges: it emits a
merge_ready marker for a human, who merges on GitHub.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from . import factory
from .harness import scenarios, target
from infra import replay

REPO = Path(__file__).resolve().parent.parent
DOCKERFILE = REPO / "infra" / "Dockerfile"


def _route(journal, finding_id=None):
    """Turn infra.replay's JSON event stream into journal events."""
    def emit(line):
        try:
            ev = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            return
        etype = ev.pop("type", "retest")
        if finding_id and etype in ("twin_deploy", "flag_check", "retest"):
            ev.setdefault("finding_id", finding_id)
        if journal:
            journal.emit(etype, **ev)
    return emit


def _harness_retest(context, phase, journal, finding_id):
    """Docker-free fallback: boot the patched app directly, replay each reference
    exploit, decide from the same server-side checks. Same verdict, no isolation."""
    app = Path(context) / "app.py"
    twin_id = "twin-proc-" + app.parent.name
    if journal:
        journal.emit("twin_deploy", twin_id=twin_id, where="local-process",
                     image="python-app", finding_id=finding_id, phase=phase)
    results = []
    for s in scenarios.ALL:
        state = REPO / "runs" / "tmp" / "gate" / phase / s.name
        with target.session(state, app_path=app) as tgt:
            s.exploit(tgt)
        v = scenarios.get(s.name).check(str(state))
        done = bool(v.get("objective_complete"))
        results.append({"check": s.name, "scenario": s.name, "objective_complete": done})
        if journal:
            journal.emit("flag_check", finding_id=s.name, scenario=s.name, phase=phase,
                         objective_complete=done, evidence=v.get("evidence", []))
            journal.emit("retest", finding_id=s.name, scenario=s.name, phase=phase,
                         objective_complete=done, status="red" if done else "green")
    any_complete = any(r["objective_complete"] for r in results)
    return results, (not any_complete if phase == "post-patch" else any_complete)


def retest(context, *, phase, journal=None, finding_id=None):
    """Rebuild a fresh twin from `context` and replay. Docker twin first (real
    isolation + the SSRF metadata chain); falls back to an in-process twin if
    Docker is unavailable. Returns (results, gate_pass)."""
    try:
        return replay.replay(context=str(context), phase=phase, dockerfile=str(DOCKERFILE),
                             emit=_route(journal, finding_id))
    except Exception as e:  # noqa: BLE001 - docker missing/daemon down -> process twin
        if journal:
            journal.emit("twin_fallback", reason=type(e).__name__, detail=str(e)[:200], phase=phase)
        return _harness_retest(context, phase, journal, finding_id)


def run_tests(journal=None, *, regression_added=0):
    """Run the pytest suite (the permanent regression + attack-replay tests)."""
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests"],
                          cwd=REPO, capture_output=True, text=True)
    out = proc.stdout + proc.stderr
    m = re.search(r"(\d+) passed", out)
    passed = int(m.group(1)) if m else 0
    failed = int((re.search(r"(\d+) failed", out) or [0, 0])[1]) if "failed" in out else 0
    total = passed + failed
    ok = proc.returncode == 0 and failed == 0
    if journal:
        journal.emit("tests", passed=passed, total=total, regression_added=regression_added,
                     ok=ok)
    return ok, passed, total


def readiness(pr, retest_green, tests_pass, verdicts, *, journal=None):
    """Compute merge-readiness and emit the pending-human marker. Never merges."""
    blockers = factory.blockers(pr, retest_green, tests_pass, verdicts)
    ready = not blockers
    approved_by = [f"{v['reviewer']}:{v['vendor']}" for v in verdicts
                   if v.get("verdict") == "approve"]
    if journal:
        journal.emit("merge_ready", pr_number=pr["number"], ready=ready, blockers=blockers,
                     approved_by=approved_by, awaiting="human",
                     rule="merge only when the replayed exploit is dead server-side, "
                          "tests pass, and both vendors approve this exact diff")
    return {"ready": ready, "blockers": blockers, "approved_by": approved_by}


def demo():
    import tempfile

    from .journal import Journal
    from . import blue

    tmp = Path(tempfile.mkdtemp())
    j = Journal(tmp / "run")
    # patched context = a copy of demo-target with the verified fix applied
    ref = blue._canonical()
    patched = tmp / "demo"
    ref.write_patched(patched)
    # force the Docker-free path to keep the self-check hermetic and fast
    results, green = _harness_retest(patched, "post-patch", j, finding_id="A1")
    assert green is True, results
    assert all(not r["objective_complete"] for r in results)

    pr = {"number": 7, "digest": "d", "finding": {}, "diff": "", "mode": "local"}
    def v(role, verdict="approve"):
        return {"reviewer": role, "vendor": "x", "verdict": verdict, "rechecked": True,
                "pr_digest": "d"}
    r = readiness(pr, True, True, [v("security"), v("correctness")], journal=j)
    assert r["ready"] and len(r["approved_by"]) == 2
    r2 = readiness(pr, False, True, [v("security"), v("correctness")], journal=j)
    assert not r2["ready"] and "retest not green" in r2["blockers"][0]
    kinds = [e["type"] for e in j.events]
    assert "twin_deploy" in kinds and "retest" in kinds and "merge_ready" in kinds
    print("gate self-check: ok (process-twin retest green, readiness gated)")


if __name__ == "__main__":
    demo()
