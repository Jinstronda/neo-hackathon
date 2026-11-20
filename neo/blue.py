"""The blue side. Read the findings NEO proved and the vulnerable source, write
the root-cause fix (parameterized query, SSRF guard, strong JWT secret) plus the
vulnerable-dependency bump, VERIFY server-side that every exploit now dies and
legitimate logins still work, then open a real PR through neo.factory.

The blue fixer model genuinely proposes the fix; we only ship a patch the
server-side checks confirm closes the finding, falling back to the canonical
FIXES.md transforms when the model's proposal does not verify. The gate, not the
model, decides. factory.open_pr emits the blue_patch event, so this module never
emits it twice.
"""
import importlib.util
import json
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
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


def _canonical():
    """The tested FIXES.md transforms (tests/_patch.py). Reuse, not rewrite."""
    spec = importlib.util.spec_from_file_location("neo_patch_ref", _PATCH_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def propose_fix(findings, app_src, req_src, ask=llm.chat_json):
    """The blue fixer model writes the fix. Returns a list of {before, after} edits
    on app.py, or [] if the model gives nothing usable."""
    msgs = [
        {"role": "system", "content":
         "You are the blue-team fixer on a security PR. Our red team already PROVED "
         "each finding on a disposable twin (server-side flag checks went red). Write "
         "the minimal root-cause fix for each finding in the given source. Copy each "
         "`before` string VERBATIM from the source so it can be located and replaced. "
         "Return only JSON."},
        {"role": "user", "content":
         "Findings:\n" + json.dumps([{k: f.get(k) for k in ("finding_id", "cls", "location")}
                                     for f in findings], indent=1)
         + "\n\napp.py:\n```\n" + app_src + "\n```\n"
         + "requirements.txt:\n```\n" + req_src + "\n```\n\n"
         'Return {"fixes":[{"finding_id":str,"before":str,"after":str,"rationale":str}]}'},
    ]
    try:
        out = ask(config.BLUE_FIXER, msgs, description="neo blue-team fixer")
    except llm.LLMError:
        return []
    return [e for e in (out.get("fixes") or []) if e.get("before") and e.get("after")]


def _apply_edits(src, edits):
    text = src
    for e in edits:
        if e["before"] not in text:
            return None
        text = text.replace(e["before"], e["after"], 1)
    return text


def _patched_app(findings, ask):
    """Try the model's fix first; fall back to the canonical transforms. Returns
    (app_text, source) where source is 'model' or 'canonical'."""
    app_src = APP.read_text()
    edits = propose_fix(findings, app_src, REQ.read_text(), ask=ask)
    if edits:
        model_text = _apply_edits(app_src, edits)
        if model_text and model_text != app_src:
            ok, _ = verify(model_text)
            if ok:
                return model_text, "model"
    return _canonical().apply(app_src), "canonical"


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


def verify(app_text):
    """Boot a patched copy, replay every reference exploit, read the server-side
    checks: every objective must now fail, and a guest login must still work."""
    tmp = Path(tempfile.mkdtemp(prefix="neo-blue-verify-"))
    try:
        shutil.copytree(DEMO, tmp / "demo", dirs_exist_ok=True)
        app = tmp / "demo" / "app.py"
        app.write_text(app_text)
        dead = {}
        for s in scenarios.ALL:
            state = tmp / "state" / s.name
            with target.session(state, app_path=app) as tgt:
                s.exploit(tgt)
            dead[s.name] = not scenarios.get(s.name).check(str(state)).get("objective_complete")
        legit = _legit_login_ok(app, tmp / "state" / "legit")
        return (all(dead.values()) and legit), {"exploits_dead": dead, "legit_login_ok": legit}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_patch(findings, ask=llm.chat_json):
    """Produce the verified patch as a clean, git-applicable unified diff plus the
    verification evidence. Touches demo-target/app.py and requirements.txt only."""
    app_text, source = _patched_app(findings, ask)
    ok, evidence = verify(app_text)
    if not ok:  # canonical is the tested floor; if even it fails, the tree drifted
        raise RuntimeError(f"no fix closed every finding: {evidence}")
    req_text = REQ.read_text().replace(OLD_PIN, NEW_PIN)
    try:
        APP.write_text(app_text)
        REQ.write_text(req_text)
        diff = subprocess.run(
            ["git", "diff", "--", "demo-target/app.py", "demo-target/requirements.txt"],
            cwd=REPO, capture_output=True, text=True, check=True).stdout
    finally:
        subprocess.run(["git", "checkout", "--", "demo-target/app.py",
                        "demo-target/requirements.txt"], cwd=REPO, capture_output=True)
    return diff, source, evidence


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


def run(findings, *, repo=None, workdir=None, journal=None, ask=llm.chat_json):
    """Write + verify the fix and open the PR. Returns {pr, patch_source,
    verification}. A real GitHub PR when repo+workdir are given; a local PR record
    otherwise. factory.open_pr emits blue_patch."""
    diff, source, evidence = build_patch(findings, ask=ask)
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
         "location": "GET /admin/whoami forged admin token", "confirmed_by": "server-side flag check",
         "request": "GET /admin/whoami", "flag_check": {"objective_complete": True}},
    ]
    # offline: the canonical fix verifies and a local PR record is written
    out = run(findings, journal=j, ask=lambda *a, **k: {"fixes": []}, )
    pr = out["pr"]
    assert pr["mode"] == "local"
    assert out["patch_source"] == "canonical"
    assert out["verification"]["legit_login_ok"] is True
    assert all(out["verification"]["exploits_dead"].values())
    assert "PyYAML>=6.0.1" in pr["diff"] and "username = ?" in pr["diff"]
    assert "Claude" not in pr["body"]
    assert [e["type"] for e in j.events] == ["blue_patch"]
    print(f"blue self-check: ok (patch verified, source={out['patch_source']}, local PR #{pr['number']})")


if __name__ == "__main__":
    demo()
