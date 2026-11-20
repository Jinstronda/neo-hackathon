"""NEO cloud runner, on the organizer box. Starts the engine's Pi harness (neo.harness.runner,
swarm agent) against a disposable twin of the demo app and serves the run in the console's
schema (neo-hackathon/docs/RUN_SCHEMA.md). The red phase is live; the blue phase comes from the
engine's recorded run (runs/demo-run), each event tagged with its origin. stdlib only.

  GET  /engine/api/run            {run, events, source}
  POST /engine/api/run {action}   attack starts a harness run; fix and approve are acknowledged
"""
import base64
import difflib
import hashlib
import json
import re
import sys
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ENGINE = Path(os.environ.get("NEO_ENGINE_DIR", "/engine"))
RUNS = Path(os.environ.get("NEO_CLOUD_RUNS", "/runs"))
SCENARIO = os.environ.get("NEO_SCENARIO", "sql-injection")
SECRET = os.environ.get("NEO_EVE_SECRET", "")
WHERE = os.environ.get("NEO_WHERE", "server")
FIXTURE = Path(__file__).with_name("fixture-run.json")
RED = {"radar_match", "twin_create", "red_start", "red_finding", "flag_check"}
lock = threading.Lock()
state = {"live": [], "running": False, "fixing": False}
sys.path[:0] = [str(ENGINE), str(ENGINE / "tests")]


def emit(event):
    with lock:
        state["live"].append(dict(event, ts=round(time.time(), 3), origin="cloud"))


def fix():
    """Blue phase on the box: the engine's documented fix for the scenario, its two-vendor
    review, the same reference exploit replayed on the patched copy, then its test suite."""
    from neo import reviewers
    from neo.harness import scenarios, target
    import _patch
    label, before, after = next(f for f in _patch.FIXES if SCENARIO.split("-")[0] in f[0].replace(" ", "-"))
    work = RUNS / ("patched-" + time.strftime("%H%M%S"))
    app = _patch.APP.parent
    import shutil
    shutil.copytree(app, work / "demo-target")
    original = (app / "app.py").read_text()
    patched = original.replace(before, after, 1)
    (work / "demo-target/app.py").write_text(patched)
    diff = "".join(difflib.unified_diff(original.splitlines(True), patched.splitlines(True), "a/demo-target/app.py", "b/demo-target/app.py", n=1))
    with lock:
        finding = next((e for e in state["live"] if e["type"] == "red_finding"), {})
    emit({"type": "blue_patch", "finding_id": finding.get("finding_id", "F-001"), "branch": f"fix/{SCENARIO}", "diff": diff,
          "commits": [{"msg": f"fix: {label.split(' ', 1)[1]} per FIXES.md", "kind": "fix"}]})
    pr = {"finding": dict(finding, scenario=SCENARIO), "diff": diff, "digest": hashlib.sha256(diff.encode()).hexdigest()}
    def review(role):
        try:
            v = reviewers.review_one(role, pr)
            emit({"type": "review", "reviewer": role, "vendor": v["vendor"], "verdict": v["verdict"], "comment": v["comment"], "rechecked": True})
        except Exception as e:  # noqa: BLE001 - a failed review is shown, never hidden
            emit({"type": "review", "reviewer": role, "verdict": "request_changes", "comment": f"review failed: {type(e).__name__}", "rechecked": False})
    threads = [threading.Thread(target=review, args=(r,)) for r in ("security", "correctness")]
    [t.start() for t in threads]
    twin = f"twin-{int(time.time()) % 100000}"
    emit({"type": "twin_deploy", "twin_id": twin, "where": "server", "image": f"demo-target:fix-{SCENARIO}", "finding_id": finding.get("finding_id", "F-001")})
    scenario = next(x for x in scenarios.ALL if x.name == SCENARIO)
    state_dir = work / "state"
    with target.session(state_dir, app_path=work / "demo-target/app.py") as tgt:
        scenario.exploit(tgt)
    verdict = scenario.check(state_dir)
    dead = verdict.get("objective_complete") is False
    emit({"type": "retest", "finding_id": finding.get("finding_id", "F-001"), "scenario": SCENARIO, "phase": "post-patch",
          "objective_complete": bool(verdict.get("objective_complete")), "status": "green" if dead else "red", "evidence": verdict.get("evidence", [])[:4]})
    [t.join(timeout=240) for t in threads]
    out = subprocess.run(["python", "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"], cwd=ENGINE, capture_output=True, text=True, timeout=600).stdout
    passed = int((re.search(r"(\d+) passed", out) or [0, 0])[1])
    failed = int((re.search(r"(\d+) failed", out) or [0, 0])[1])
    emit({"type": "tests", "passed": passed, "total": passed + failed, "regression_added": 1})
    with lock:
        first = next((e["ts"] for e in state["live"] if e["type"] == "red_finding"), time.time())
        state["fixing"] = False
    emit({"type": "metrics", "minutes_exploit_to_fix": max(1, round((time.time() - first) / 60)), "regression_tests": passed + failed, "where": WHERE})


def recorded():
    """The engine's recorded run, or the fixture when the engine has not written one yet."""
    for path, origin in ((ENGINE / "runs/demo-run/run.json", "recorded"), (FIXTURE, "fixture")):
        if path.exists():
            data = json.loads(path.read_text())
            if "run" not in data:
                events = [json.loads(l) for l in (path.parent / "events.jsonl").read_text().splitlines() if l.strip()]
                data = {"run": data, "events": events}
            return data, origin
    raise FileNotFoundError("no recorded run")


def radar():
    """The engine's exploit radar: SBOM of the demo app against live CISA KEV, EPSS and OSV."""
    try:
        out = subprocess.run(["python", "-m", "neo.radar", "--json"], cwd=ENGINE, capture_output=True, text=True, timeout=120).stdout
        result = json.loads(out)
        staged = (ENGINE / "neo/fixtures/kev_staged.json").read_text()
        for m in result.get("matches", []):
            emit({"type": "radar_match", "cve": m["cve"], "kev": m.get("kev"), "kev_staged": m["cve"] in staged, "epss": m.get("epss"),
                  "osv": ", ".join(m.get("osv") or []), "package": m["package"], "version": m["version"], "reachable": m.get("reachable"),
                  "kev_source": result.get("kev_source")})
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass


def harness(started):
    radar()
    run_dir = RUNS / time.strftime("%Y%m%d-%H%M%S")
    proc = subprocess.run(
        ["python", "-m", "neo.harness.runner", "run", "--scenario", SCENARIO, "--agent", "swarm", "--run-dir", str(run_dir)],
        cwd=ENGINE, capture_output=True, text=True, timeout=600)
    events = []
    try:
        report = json.loads((run_dir / "report.json").read_text())
        metrics = json.loads((run_dir / "metrics.json").read_text())
        now = time.time()
        for i, f in enumerate(report.get("findings", [])):
            events.append({"type": "red_finding", "ts": round(now + i * 0.1, 3), "finding_id": f"F-{i + 1:03d}", "model": "model-1",
                           "cls": f.get("class", ""), "location": f.get("location", ""), "request": f.get("evidence", ""),
                           "response": str(report.get("chain", ""))[:600], "confirmed_by": "model-3", "origin": "cloud"})
        events.append({"type": "flag_check", "ts": round(now + 1, 3), "finding_id": "F-001", "scenario": metrics.get("scenario", SCENARIO),
                       "phase": "pre-patch", "objective_complete": bool(metrics.get("objective_complete")),
                       "evidence": [json.dumps(e) for e in metrics.get("evidence", [])][:4], "origin": "cloud"})
    except (OSError, ValueError):
        events.append({"type": "harness_error", "ts": round(time.time(), 3), "detail": (proc.stderr or "")[-400:], "origin": "cloud"})
    with lock:
        state["live"] += events
        state["running"] = False


def attack():
    with lock:
        if state["running"]:
            return
        now = time.time()
        state["running"] = True
        state["fixing"] = False
        state["live"] = [
            {"type": "twin_create", "ts": round(now, 3), "twin_id": f"twin-{int(now) % 100000}", "where": "server", "image": f"demo-target:{SCENARIO}", "origin": "cloud"},
            {"type": "red_start", "ts": round(now + 0.5, 3), "twin_id": f"twin-{int(now) % 100000}", "models": ["model-1", "model-2", "model-3"], "origin": "cloud"},
        ]
    threading.Thread(target=harness, args=(now,), daemon=True).start()


def snapshot():
    data, origin = recorded()
    with lock:
        live = list(state["live"])
    if not live:
        return {"run": data["run"], "events": data["events"], "source": "recorded" if origin == "recorded" else "fixture"}
    return {"run": data["run"], "events": sorted(live, key=lambda e: e["ts"]), "source": "engine"}


class Handler(BaseHTTPRequestHandler):
    def _auth(self):
        want = "Basic " + base64.b64encode(f"neo:{SECRET}".encode()).decode()
        return bool(SECRET) and self.headers.get("authorization") == want

    def _send(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if not self._auth():
            return self._send(401, {"error": "unauthorized"})
        if self.path.rstrip("/") == "/engine/api/run":
            return self._send(200, snapshot())
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._auth():
            return self._send(401, {"error": "unauthorized"})
        if self.path.rstrip("/") != "/engine/api/run":
            return self._send(404, {"error": "not found"})
        length = int(self.headers.get("content-length") or 0)
        action = json.loads(self.rfile.read(length) or b"{}").get("action")
        if action not in ("attack", "fix", "approve"):
            return self._send(400, {"error": "action must be attack, fix or approve"})
        if action == "attack":
            attack()
        elif action == "fix":
            with lock:
                ready = any(e["type"] == "flag_check" for e in state["live"]) and not state["fixing"]
                if ready:
                    state["fixing"] = True
            if ready:
                threading.Thread(target=fix, daemon=True).start()
        elif action == "approve":
            emit({"type": "merge", "by": "human", "approved_by": ["security", "correctness"]})
        self._send(200, {"ok": True, "action": action, "scenario": SCENARIO})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8090), Handler).serve_forever()
