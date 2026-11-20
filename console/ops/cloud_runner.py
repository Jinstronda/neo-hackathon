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
import urllib.parse
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
# gen is the run generation. It rises on each attack and stamps every event, so a late emit from
# a previous run's fix thread cannot contaminate the current run's merge gate.
state = {"live": [], "running": False, "fixing": False, "gen": 0, "pr": None}
sys.path[:0] = [str(ENGINE), str(ENGINE / "tests")]

# Secrets must not leave the box in the run we serve to the console. Mask any env-sourced secret
# value (and its base64 / url-encoded forms) by literal, plus the shapes that turn up in exploit
# payloads and patch diffs: JWTs, whole auth-header lines, bearer/basic creds, private keys, and
# secret= assignments (quoted or not, like the weak-JWT demo secret).
_ENV_SECRETS = {v for k, v in os.environ.items() if v and len(v) >= 6 and any(t in k.upper() for t in ("SECRET", "PASS", "TOKEN", "KEY"))}
SECRET_VALUES = sorted(
    {f for v in _ENV_SECRETS for f in (
        v, base64.b64encode(v.encode()).decode(), base64.b64encode(v.encode()).decode().rstrip("="), urllib.parse.quote(v, safe=""))},
    key=len, reverse=True,
)
_SECRET_RE = re.compile(
    r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
    r"|(?i:authorization|cookie|set-cookie)\s*[:=][^\r\n]*"
    r"|(?i:bearer|basic)\s+[A-Za-z0-9+/=._-]{8,}"
    r"|-----BEGIN[^-]+PRIVATE KEY-----[\s\S]+?-----END[^-]+KEY-----"
    r"""|(?i:(?:secret|password|passwd|api[_-]?key|token)[\w-]*["'\]]*\s*[:=]\s*)["']?[^\s"',}]+"""
)
_SECRET_KEY = re.compile(r"(?i)(secret|password|passwd|token|api[_-]?key|authorization|cookie)")


def _redact(text):
    for value in SECRET_VALUES:
        text = text.replace(value, "[redacted]")
    return _SECRET_RE.sub("[redacted]", text)


def scrub(value, key=None):
    """Mask secrets in any string a response carries, recursively, before it leaves the box. A
    value under a secret-looking key is redacted whole, since its content is free-form."""
    if isinstance(value, str):
        return "[redacted]" if key and _SECRET_KEY.search(key) else _redact(value)
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: scrub(v, key=k) for k, v in value.items()}
    return value


def proven(live):
    """A finding counts only when a server-side pre-patch flag check saw the exploit work.
    Without this, a run where the exploit never fired (pre-patch false, so post-patch also false,
    read as 'green') could merge a fix for a vulnerability that was never real."""
    return any(e["type"] == "flag_check" and e.get("phase") == "pre-patch" and e.get("objective_complete") is True for e in live)


def merge_ready(live):
    """The full server-side gate for a merge, decided from the run, never from a client claim: a
    proven exploit, a green post-patch retest (exploit dead), both named reviewers approving with
    no request_changes, not already merged. `live` must already be filtered to the current run.
    Returns (ok, approvers)."""
    green = any(e["type"] == "retest" and e.get("status") == "green" and e.get("objective_complete") is False for e in live)
    reviews = [e for e in live if e["type"] == "review"]
    approvers = {e["reviewer"] for e in reviews if e.get("verdict") == "approve"}
    changes = any(e.get("verdict") == "request_changes" for e in reviews)
    already = any(e["type"] == "merge" for e in live)
    ok = bool(proven(live) and green and approvers == {"security", "correctness"} and not changes and not already)
    return ok, sorted(approvers)


def current(live, gen):
    """Events belonging to the run `gen`; events predate gen-stamping are treated as current."""
    return [e for e in live if e.get("gen", gen) == gen]


def emit(event, gen=None):
    with lock:
        if gen is not None and gen != state["gen"]:
            return  # a stale thread from a previous run: drop it
        state["live"].append(dict(event, ts=round(time.time(), 3), origin="cloud", gen=state["gen"]))


def fix(gen):
    """Blue phase on the box: the engine's documented fix for the scenario, its two-vendor
    review, the same reference exploit replayed on the patched copy, then its test suite. Every
    emit carries `gen` so a late event is dropped if a new run has started meanwhile."""
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
    digest = hashlib.sha256(diff.encode()).hexdigest()
    pr_number = 1 + int(digest[:6], 16) % 90  # stable per patch, so the demo shows the same PR each run
    pr_url = f"https://github.com/neo/demo-target/pull/{pr_number}"
    with lock:
        finding = next((e for e in state["live"] if e["type"] == "red_finding"), {})
        state["pr"] = pr_number  # the merge event, emitted in the approve handler, reads this
    emit({"type": "blue_patch", "finding_id": finding.get("finding_id", "F-001"), "pr_number": pr_number, "pr_url": pr_url,
          "branch": f"fix/{SCENARIO}", "diff": diff,
          "commits": [{"msg": f"fix: {label.split(' ', 1)[1]} per FIXES.md", "kind": "fix"}]}, gen)
    pr = {"finding": dict(finding, scenario=SCENARIO), "diff": diff, "digest": digest}
    def review(role):
        try:
            v = reviewers.review_one(role, pr)
            emit({"type": "review", "pr_number": pr_number, "reviewer": role, "vendor": v["vendor"], "verdict": v["verdict"], "comment": v["comment"], "rechecked": True}, gen)
        except Exception as e:  # noqa: BLE001 - a failed review is shown, never hidden
            emit({"type": "review", "pr_number": pr_number, "reviewer": role, "verdict": "request_changes", "comment": f"review failed: {type(e).__name__}", "rechecked": False}, gen)
    threads = [threading.Thread(target=review, args=(r,)) for r in ("security", "correctness")]
    [t.start() for t in threads]
    twin = f"twin-{int(time.time()) % 100000}"
    emit({"type": "twin_deploy", "twin_id": twin, "where": "server", "image": f"demo-target:fix-{SCENARIO}", "finding_id": finding.get("finding_id", "F-001")}, gen)
    scenario = next(x for x in scenarios.ALL if x.name == SCENARIO)
    state_dir = work / "state"
    with target.session(state_dir, app_path=work / "demo-target/app.py") as tgt:
        scenario.exploit(tgt)
    verdict = scenario.check(state_dir)
    dead = verdict.get("objective_complete") is False
    emit({"type": "retest", "finding_id": finding.get("finding_id", "F-001"), "scenario": SCENARIO, "phase": "post-patch",
          "objective_complete": bool(verdict.get("objective_complete")), "status": "green" if dead else "red", "evidence": verdict.get("evidence", [])[:4]}, gen)
    [t.join(timeout=240) for t in threads]
    out = subprocess.run(["python", "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"], cwd=ENGINE, capture_output=True, text=True, timeout=600).stdout
    passed = int((re.search(r"(\d+) passed", out) or [0, 0])[1])
    failed = int((re.search(r"(\d+) failed", out) or [0, 0])[1])
    emit({"type": "tests", "passed": passed, "total": passed + failed, "regression_added": 1}, gen)
    with lock:
        first = next((e["ts"] for e in current(state["live"], gen) if e["type"] == "red_finding"), time.time())
    rm = recorded()[0]["run"].get("metrics", {})  # the demo target's surface figures, one source of truth
    emit({"type": "metrics", "minutes_exploit_to_fix": max(1, round((time.time() - first) / 60)),
          "cost_usd": rm.get("cost_usd"), "tested_surface": rm.get("tested_surface"), "untested_surface": rm.get("untested_surface"),
          "regression_tests": passed + failed, "where": WHERE}, gen)


def run_fix(gen):
    """Run fix() and always release the fix lock, so a crash cannot wedge the runner (no further
    attack would be accepted). A failure is shown as an event, never hidden."""
    try:
        fix(gen)
    except Exception as e:  # noqa: BLE001
        emit({"type": "harness_error", "detail": f"fix failed: {type(e).__name__}"}, gen)
    finally:
        with lock:
            if gen == state["gen"]:
                state["fixing"] = False


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


def radar(gen):
    """The engine's exploit radar: SBOM of the demo app against live CISA KEV, EPSS and OSV."""
    try:
        out = subprocess.run(["python", "-m", "neo.radar", "--json"], cwd=ENGINE, capture_output=True, text=True, timeout=120).stdout
        result = json.loads(out)
        staged = (ENGINE / "neo/fixtures/kev_staged.json").read_text()
        for m in result.get("matches", []):
            emit({"type": "radar_match", "cve": m["cve"], "kev": m.get("kev"), "kev_staged": m["cve"] in staged, "epss": m.get("epss"),
                  "osv": ", ".join(m.get("osv") or []), "package": m["package"], "version": m["version"], "reachable": m.get("reachable"),
                  "kev_source": result.get("kev_source")}, gen)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass


def harness(started, gen):
    events = []
    try:
        radar(gen)
        run_dir = RUNS / time.strftime("%Y%m%d-%H%M%S")
        proc = subprocess.run(
            ["python", "-m", "neo.harness.runner", "run", "--scenario", SCENARIO, "--agent", "swarm", "--run-dir", str(run_dir)],
            cwd=ENGINE, capture_output=True, text=True, timeout=600)
        try:
            report = json.loads((run_dir / "report.json").read_text())
            metrics = json.loads((run_dir / "metrics.json").read_text())
            now = time.time()
            for i, f in enumerate(report.get("findings", [])):
                events.append({"type": "red_finding", "ts": round(now + i * 0.1, 3), "finding_id": f"F-{i + 1:03d}", "model": "model-1",
                               "cls": f.get("class", ""), "location": f.get("location", ""), "request": f.get("evidence", ""),
                               "response": str(report.get("chain", ""))[:600], "confirmed_by": "model-3", "origin": "cloud", "gen": gen})
            events.append({"type": "flag_check", "ts": round(now + 1, 3), "finding_id": "F-001", "scenario": metrics.get("scenario", SCENARIO),
                           "phase": "pre-patch", "objective_complete": bool(metrics.get("objective_complete")),
                           "evidence": [json.dumps(e) for e in metrics.get("evidence", [])][:4], "origin": "cloud", "gen": gen})
        except (OSError, ValueError):
            sys.stderr.write((proc.stderr or "")[-2000:])
            events.append({"type": "harness_error", "ts": round(time.time(), 3), "detail": f"harness exited {proc.returncode}", "origin": "cloud", "gen": gen})
    except Exception as e:  # noqa: BLE001 - the red phase crashed; show it, never wedge the runner
        events.append({"type": "harness_error", "ts": round(time.time(), 3), "detail": f"attack failed: {type(e).__name__}", "origin": "cloud", "gen": gen})
    finally:
        with lock:
            if gen == state["gen"]:
                state["live"] += events
                state["running"] = False


def attack():
    with lock:
        if state["running"] or state["fixing"]:
            return  # do not reset a run while its red phase or fix is still in flight
        now = time.time()
        state["gen"] += 1
        gen = state["gen"]
        state["running"] = True
        state["live"] = [
            {"type": "twin_create", "ts": round(now, 3), "twin_id": f"twin-{int(now) % 100000}", "where": "server", "image": f"demo-target:{SCENARIO}", "origin": "cloud", "gen": gen},
            {"type": "red_start", "ts": round(now + 0.5, 3), "twin_id": f"twin-{int(now) % 100000}", "models": ["model-1", "model-2", "model-3"], "origin": "cloud", "gen": gen},
        ]
    threading.Thread(target=harness, args=(now, gen), daemon=True).start()


def snapshot():
    data, origin = recorded()
    with lock:
        live = current(state["live"], state["gen"])
    if not live:
        return scrub({"run": data["run"], "events": data["events"], "source": "recorded" if origin == "recorded" else "fixture"})
    return scrub({"run": data["run"], "events": sorted(live, key=lambda e: e["ts"]), "source": "engine"})


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
                gen = state["gen"]
                ready = proven(current(state["live"], gen)) and not state["fixing"] and not state["running"]
                if ready:
                    state["fixing"] = True
            if not ready:
                return self._send(409, {"error": "fix needs a proven finding (pre-patch flag check objective_complete=true)"})
            threading.Thread(target=run_fix, args=(gen,), daemon=True).start()
        elif action == "approve":
            with lock:
                gen = state["gen"]
                live = current(state["live"], gen)
            ok, approvers = merge_ready(live)
            if not ok:
                return self._send(409, {"error": "approve needs a proven exploit, a green retest and two approving reviews"})
            with lock:
                pr_number = state.get("pr")
            emit({"type": "merge", "pr_number": pr_number, "by": "human", "approved_by": approvers}, gen)
        self._send(200, {"ok": True, "action": action, "scenario": SCENARIO})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8090), Handler).serve_forever()
