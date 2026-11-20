"""The blue side. Read the findings NEO proved and the vulnerable source, write
the root-cause fix (parameterized query, SSRF guard, strong JWT secret) plus the
vulnerable-dependency bump, verify server-side on a fresh copy that every exploit
now dies and legitimate logins still work, then open the PR through neo.factory.

The fixer is a loop, not one shot. After each failed verify the model is told
exactly which exploits still landed and whether the guest login broke, and is
asked again, up to max_fix_attempts. If no model patch verifies, the canonical
FIXES.md transform is the floor. Only a patch verify() proves closes every finding
is ever opened as a PR: the server-side checks decide, never the model.

Every attempt is journaled as fix_attempt. factory.open_pr emits blue_patch, so
this module never emits it twice.
"""
import contextlib
import importlib.util
import json
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

from . import config, factory, llm
from .harness import scenarios, target

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "demo-target"
APP = DEMO / "app.py"
REQ = DEMO / "requirements.txt"
_PATCH_PY = REPO / "tests" / "_patch.py"

OLD_PIN = "PyYAML==5.3.1"
NEW_PIN = "PyYAML>=6.0.1"

_SYSTEM = (
    "You are the blue-team fixer on a security PR. Our red team already PROVED each "
    "finding on a disposable twin (server-side flag checks went red). Write the minimal "
    "root-cause fix for each finding in the given source. Copy each `before` string "
    "VERBATIM from the source so it can be located and replaced. Return only JSON.")
_SHAPE = 'Return {"fixes":[{"finding_id":str,"before":str,"after":str,"rationale":str}]}'


def _canonical():
    """The tested FIXES.md transforms (tests/_patch.py). Reuse, not rewrite."""
    spec = importlib.util.spec_from_file_location("neo_patch_ref", _PATCH_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fixer_messages(findings: list[dict], app_src: str, req_src: str) -> list[dict]:
    """The opening turn of the conversation with the fixer model."""
    brief = [{k: f.get(k) for k in ("finding_id", "cls", "location")} for f in findings]
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content":
         "Findings:\n" + json.dumps(brief, indent=1)
         + "\n\napp.py:\n```\n" + app_src + "\n```\n"
         + "requirements.txt:\n```\n" + req_src + "\n```\n\n" + _SHAPE},
    ]


def _ask_fixer(ask, msgs):
    """The fixer's raw JSON answer, or None when the gateway failed."""
    try:
        out = ask(config.BLUE_FIXER, msgs, description="neo blue-team fixer")
    except llm.LLMError:
        return None
    return out if isinstance(out, dict) else None


def _edits(out):
    """The usable {before, after} edits in a fixer answer (untrusted model output)."""
    fixes = (out or {}).get("fixes")
    if not isinstance(fixes, list):
        return []
    return [e for e in fixes if isinstance(e, dict) and isinstance(e.get("after"), str)
            and isinstance(e.get("before"), str) and e["before"]]


def propose_fix(findings: list[dict], app_src: str, req_src: str,
                ask: Callable | None = None) -> list[dict]:
    """One proposal from the fixer model: a list of {before, after} edits on app.py,
    or [] if the model gives nothing usable."""
    return _edits(_ask_fixer(ask or llm.chat_json, fixer_messages(findings, app_src, req_src)))


def _apply_edits(src, edits):
    text = src
    for e in edits:
        if e["before"] not in text:
            return None
        text = text.replace(e["before"], e["after"], 1)
    return text


def _untested(reason):
    return {"exploits_dead": {}, "legit_login_ok": None, "error": reason}


def _try_model(app_src, edits):
    """Apply one proposal and verify it. Returns (patched_text, ok, evidence)."""
    if not edits:
        return None, False, _untested("the fixer proposed no usable edits")
    text = _apply_edits(app_src, edits)
    if text is None:
        return None, False, _untested("a `before` string was not found verbatim in app.py")
    if text == app_src:
        return None, False, _untested("the edits change nothing")
    ok, evidence = verify(text)
    return text, ok, evidence


def _feedback(evidence):
    """Tell the fixer exactly what the fresh-copy verify saw, so it can try again."""
    alive = sorted(s for s, dead in evidence["exploits_dead"].items() if not dead)
    notes = []
    if evidence.get("error"):
        notes.append(f"Your patch could not be verified: {evidence['error']}.")
    if alive:
        notes.append("We replayed every exploit on a fresh copy of the patched app. These "
                     f"still landed (the server-side flag check fired): {', '.join(alive)}.")
    if evidence.get("legit_login_ok") is False and not evidence.get("error"):
        notes.append("The legitimate guest login (guest/guest) no longer works. "
                     "Valid logins must keep working.")
    return " ".join(notes) + (" Return the complete set of fixes again, each `before` "
                              "copied verbatim from the original app.py above. " + _SHAPE)


def _record(journal, attempt, of, source, ok, evidence):
    rec = {"attempt": attempt, "of": of, "source": source, "ok": ok,
           "exploits_dead": evidence.get("exploits_dead", {}),
           "legit_login_ok": evidence.get("legit_login_ok")}
    if evidence.get("error"):
        rec["error"] = evidence["error"]
    if journal:
        journal.emit("fix_attempt", **rec)
    return rec


def _patched_app(findings, ask, *, journal=None, max_fix_attempts=3):
    """Ask, verify on a fresh copy, feed back what still landed, ask again. Falls
    back to the canonical transform. Returns (app_text, source, evidence), with
    every attempt in evidence["attempts"]."""
    app_src = APP.read_text()
    msgs = fixer_messages(findings, app_src, REQ.read_text())
    attempts = []
    for n in range(1, max_fix_attempts + 1):
        out = _ask_fixer(ask, msgs)
        edits = _edits(out)
        text, ok, evidence = _try_model(app_src, edits)
        attempts.append(_record(journal, n, max_fix_attempts, "model", ok, evidence))
        if ok:
            return text, "model", {**evidence, "attempts": attempts}
        if not edits:
            break  # the fixer is down or proposed nothing: no feedback to give
        msgs = msgs + [{"role": "assistant", "content": json.dumps(out)},
                       {"role": "user", "content": _feedback(evidence)}]
    text = _canonical().apply(app_src)
    ok, evidence = verify(text)
    attempts.append(_record(journal, len(attempts) + 1, max_fix_attempts, "canonical",
                            ok, evidence))
    if not ok:  # canonical is the tested floor; if even it fails, the tree drifted
        raise RuntimeError(f"no fix closed every finding: {evidence}")
    return text, "canonical", {**evidence, "attempts": attempts}


def _post(base_url, path, form):
    data = urllib.parse.urlencode(form).encode()
    with urllib.request.urlopen(base_url + path, data=data, timeout=5) as r:
        return r.status, json.loads(r.read())


def _legit_login_ok(app_path, state_dir):
    with target.session(state_dir, app_path=app_path) as tgt:
        try:
            status, body = _post(tgt.base_url, "/login", {"username": "guest", "password": "guest"})
        except Exception:  # noqa: BLE001
            return False
    return status == 200 and body.get("role") == "guest" and bool(body.get("token"))


def _exploit_dead(scenario, app_path, state_dir):
    """Replay one reference exploit on a fresh boot; the server-side check rules.
    A request the patched app refuses or drops is a dead exploit, not a crash."""
    with (target.session(state_dir, app_path=app_path) as tgt,
          contextlib.suppress(OSError, ValueError)):
        scenario.exploit(tgt)
    return not scenario.check(str(state_dir)).get("objective_complete")


def verify(app_text: str) -> tuple[bool, dict]:
    """Boot a patched copy, replay every reference exploit, read the server-side
    checks: every objective must now fail, and a guest login must still work. A
    patch that does not compile or boot fails, with the reason as evidence."""
    tmp = Path(tempfile.mkdtemp(prefix="neo-blue-verify-"))
    try:
        compile(app_text, "app.py", "exec")
        shutil.copytree(DEMO, tmp / "demo", ignore=shutil.ignore_patterns("__pycache__"))
        app = tmp / "demo" / "app.py"
        app.write_text(app_text)
        dead = {s.name: _exploit_dead(s, app, tmp / "state" / s.name) for s in scenarios.ALL}
        legit = _legit_login_ok(app, tmp / "state" / "legit")
    except (SyntaxError, ValueError, RuntimeError) as e:
        return False, {"exploits_dead": {}, "legit_login_ok": False,
                       "error": f"the patched app did not boot: {e}"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return (all(dead.values()) and legit), {"exploits_dead": dead, "legit_login_ok": legit}


def _diff(app_text, req_text):
    """A git-applicable diff of demo-target, built from scratch copies so the shared
    working tree is never written. Byte-identical to `git diff` in the repo."""
    with tempfile.TemporaryDirectory(prefix="neo-blue-diff-") as tmp:
        for side, texts in (("a", None), ("b", {APP.name: app_text, REQ.name: req_text})):
            d = Path(tmp) / side / DEMO.name
            d.mkdir(parents=True)
            for src in (APP, REQ):
                shutil.copy2(src, d / src.name)  # keeps the file mode git records
                if texts:
                    (d / src.name).write_text(texts[src.name])
        out = subprocess.run(["git", "diff", "--no-index", "--no-prefix", "--no-color",
                              "--no-ext-diff", "a", "b"], cwd=tmp, capture_output=True, text=True)
    if out.returncode > 1:  # 1 means "files differ"
        raise RuntimeError(f"git diff failed: {out.stderr.strip()[:200]}")
    return out.stdout


def build_patch(findings: list[dict], ask: Callable | None = None, *, journal=None,
                max_fix_attempts: int = 3) -> tuple[str, str, dict]:
    """Produce the verified patch as a clean, git-applicable unified diff plus the
    verification evidence. Touches demo-target/app.py and requirements.txt only.
    Returns (diff, source, evidence); source is "model" or "canonical"."""
    app_text, source, evidence = _patched_app(findings, ask or llm.chat_json, journal=journal,
                                              max_fix_attempts=max_fix_attempts)
    return _diff(app_text, REQ.read_text().replace(OLD_PIN, NEW_PIN)), source, evidence


def _primary(findings):
    """The headline finding for the PR. One comprehensive PR closes every proven
    finding, headlined by SQLi; the diff carries the SSRF and JWT hardening too."""
    by_scn = {f["scenario"]: f for f in findings}
    head = by_scn.get("sql-injection", findings[0])
    classes = ", ".join(sorted({f["cls"] for f in findings}))
    locations = "; ".join(sorted({f["location"] for f in findings}))
    summary = "\n".join(f"- {f['cls']} at {f['location']} "
                        f"(proven server-side, confirmed_by={f['confirmed_by']})"
                        for f in findings)
    return {**head, "cls": classes, "location": locations,
            "request": "NEO proved these on a disposable twin:\n" + summary,
            "all_findings": findings}


def run(findings: list[dict], *, repo: str | None = None, workdir: Path | None = None,
        journal=None, ask: Callable | None = None, max_fix_attempts: int = 3) -> dict:
    """Write and verify the fix, then open the PR. Returns {pr, patch_source,
    verification}. A real GitHub PR when repo+workdir are given; a local PR record
    otherwise. ask=None means the real llm.chat_json. factory.open_pr emits
    blue_patch."""
    diff, source, evidence = build_patch(findings, ask, journal=journal,
                                         max_fix_attempts=max_fix_attempts)
    pr = factory.open_pr(_primary(findings), diff, journal=journal, repo=repo,
                         workdir=workdir, base="master")
    return {"pr": pr, "patch_source": source, "verification": evidence}


def demo():
    from .journal import Journal

    tmp = Path(tempfile.mkdtemp())
    j = Journal(tmp / "run")
    findings = [
        {"finding_id": "A1", "scenario": "sql-injection", "cls": "sql-injection",
         "location": "POST /login username parameter", "confirmed_by": "server-side flag check",
         "request": "POST /login", "exploit": "demo-target/exploit_sqli.py",
         "check": "checks/check_sqli.py", "flag_check": {"objective_complete": True}},
        {"finding_id": "B1", "scenario": "ssrf-metadata", "cls": "ssrf",
         "location": "POST /import-avatar url parameter", "confirmed_by": "server-side flag check",
         "request": "POST /import-avatar", "flag_check": {"objective_complete": True}},
        {"finding_id": "C1", "scenario": "weak-jwt-secret", "cls": "weak-jwt-secret",
         "location": "GET /admin/whoami forged admin token",
         "confirmed_by": "server-side flag check",
         "request": "GET /admin/whoami", "flag_check": {"objective_complete": True}},
    ]
    # offline: the fixer proposes nothing, the canonical fix verifies, a local PR record
    out = run(findings, journal=j, ask=lambda *a, **k: {"fixes": []})
    pr = out["pr"]
    assert pr["mode"] == "local"
    assert out["patch_source"] == "canonical"
    assert out["verification"]["legit_login_ok"] is True
    assert all(out["verification"]["exploits_dead"].values())
    assert "PyYAML>=6.0.1" in pr["diff"] and "username = ?" in pr["diff"]
    assert "Claude" not in pr["body"]
    assert [e["type"] for e in j.events] == ["fix_attempt", "fix_attempt", "blue_patch"]
    assert [(e["source"], e["ok"]) for e in j.events[:2]] == [("model", False), ("canonical", True)]
    print(f"blue self-check: ok (patch verified, source={out['patch_source']}, "
          f"local PR #{pr['number']})")


if __name__ == "__main__":
    demo()
