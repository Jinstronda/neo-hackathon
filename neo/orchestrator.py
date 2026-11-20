"""The NEO closed loop, one run end to end:

  radar matches a dropped CVE to our SBOM -> the red swarm proves the exploits on
  disposable twins (server-side flag checks go red) -> a human approves the fix ->
  blue writes the patch, verifies it on a fresh copy and loops back to the model
  while any exploit still lands -> two vendors review the exact diff -> a fresh
  twin built from that diff replays the same exploits (they must fail) -> tests
  pass -> the loop stops at a merge a human presses.

It runs in three phases, so a chat agent can stop between them and ask:

  ctx = start(run_id)     fresh runs/<id>/ and its journal
  attack(ctx)             radar + red swarm; returns the proven findings
  remediate(ctx)          blue, review, retest, gate, metrics, run.json

loop() runs all three. Writes runs/<id>/events.jsonl and run.json per
docs/RUN_SCHEMA.md. Server-side flag checks, never an agent's report, decide
red/green. This module never merges.
"""
import datetime
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from . import blue, config, env, factory, gate, llm, radar, red, shots, term
from .harness import agent as agent_mod
from .journal import Journal

REPO = Path(__file__).resolve().parent.parent
RUNS = REPO / "runs"
AGENTS = ("swarm", "mock")
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
UNTESTED_SURFACE = 2  # GET /me, GET / have no dedicated adversarial scenario yet

STEPS = [
    {"key": "radar", "title": "Radar match", "live": False, "events": ["radar_match"]},
    {"key": "red", "title": "NEO proves the exploit", "live": True,
     "events": ["red_start", "red_finding", "flag_check"]},
    {"key": "blue", "title": "Blue opens the patch PR", "live": True,
     "events": ["fix_approval", "fix_attempt", "blue_patch"]},
    {"key": "review", "title": "Two reviewers check the PR", "live": True, "events": ["review"]},
    {"key": "retest", "title": "Twin rebuilt, exploit replayed", "live": True,
     "events": ["twin_deploy", "retest", "tests"]},
    {"key": "merge", "title": "Human merges", "live": False, "events": ["merge_ready", "merge"]},
]


# Offline stand-in for llm.chat_json --------------------------------------------

def _first_added_line(messages):
    """The first real "+" line of the diff quoted in a reviewer prompt."""
    for line in messages[-1]["content"].splitlines():
        if line.startswith("+") and not line.startswith("+++") and line[1:].strip():
            return line[1:].strip()
    return ""


def _offline_ask(model, messages, *, description, timeout=120):
    """chat_json stand-in for demos and tests with no gateway. The fixer proposes no
    edits, so the canonical FIXES.md transform ships. Each reviewer approves and
    quotes a real "+" line of the diff, so decide() can check its span. The
    server-side retest and the tests still decide whether the PR is ready."""
    if "fixer" in description:
        return {"fixes": []}
    claim = {"claim": "offline stand-in: no model reviewed this diff",
             "span": _first_added_line(messages)}
    if "draft" in description:
        return {"verdict": "approve", "comment": "Offline stand-in review, no model call.",
                "claims": [claim]}
    return {"checks": [{**claim, "holds": True}], "exploit_still_works": False,
            "verified": "offline stand-in: the server-side retest decides",
            "verdict": "approve"}


OFFLINE_ASK = _offline_ask


# The three phases -------------------------------------------------------------

def start(run_id: str, *, models: list[str] | None = None, live: bool = True,
          agent: str = "swarm", ask: Callable | None = None) -> dict:
    """A fresh run: wipes runs/<run_id>/, opens its journal and, when live, prints
    every event. agent="mock" drives red with the deterministic reference chain (no
    LLM). ask is a chat_json-compatible callable for blue and the reviewers; None
    means the real llm.chat_json."""
    if not _RUN_ID.fullmatch(run_id or ""):
        raise ValueError(f"run_id must be letters, digits, '.', '_' or '-': {run_id!r}")
    if agent not in AGENTS:
        raise ValueError(f"agent must be one of {AGENTS}: {agent!r}")
    env.load()
    models = list(models or config.RED_SWARM or (["reference"] if agent == "mock" else []))
    if not models:
        raise ValueError("no red models: set NEO_RED_SWARM in .env, or use agent='mock'")
    run_dir = RUNS / run_id
    shutil.rmtree(run_dir, ignore_errors=True)
    journal = Journal(run_dir)
    if live:
        term.attach(journal)
    return {"id": run_id, "dir": run_dir, "journal": journal, "models": models,
            "agent": agent, "ask": ask, "usage_base": llm.usage_summary()}


def _mock_factory(_models):
    return agent_mod.mock_agent


def attack(ctx: dict) -> list[dict]:
    """Radar, then the red swarm proves what it can on disposable twins. Returns the
    proven findings, [] when nothing landed."""
    j = ctx["journal"]
    scan = radar.scan()
    top = scan["matches"][0] if scan["matches"] else {}
    j.emit("radar_match", cve=top.get("cve"), kev=top.get("kev"), epss=top.get("epss"),
           osv=top.get("osv", []), package=top.get("package"), version=top.get("version"),
           reachable=top.get("reachable"), kev_source=scan.get("kev_source"))
    agent_factory = _mock_factory if ctx["agent"] == "mock" else agent_mod.swarm_agent
    findings = red.run(ctx["models"], run_root=ctx["dir"] / "red", journal=j,
                       agent_factory=agent_factory)
    t_exploit = next((e["ts"] for e in j.events
                      if e["type"] == "flag_check" and e.get("objective_complete")), None)
    ctx.update(radar=top, findings=findings, t_exploit=t_exploit)
    return findings


def record_approval(ctx: dict, approved: bool, *, by: str = "human") -> bool:
    """Record the fix decision as fix_approval. remediate() refuses to run blue
    without an approval, and records an "auto" one when none was given."""
    ctx["approval"] = {"approved": bool(approved), "by": by}
    ctx["journal"].emit("fix_approval", **ctx["approval"])
    return bool(approved)


def _require_approval(ctx):
    if "approval" not in ctx:
        record_approval(ctx, True, by="auto")
    if not ctx["approval"]["approved"]:
        raise PermissionError("the fix was not approved; blue does not run")


def remediate(ctx: dict, *, repo: str | None = None, screenshots: bool = False,
              max_fix_attempts: int = 3) -> dict:
    """Blue (with loop-back), two-vendor review, retest, gate, metrics, run.json.
    repo=None writes a local PR record and never touches GitHub. Returns the run
    summary."""
    findings = ctx.get("findings")
    if not findings:
        raise ValueError("nothing proven to fix: run attack(ctx) first")
    _require_approval(ctx)
    j = ctx["journal"]
    workdir = _checkout(ctx["id"], repo, findings) if repo else None
    out = blue.run(findings, repo=repo, workdir=workdir, journal=j, ask=ctx["ask"],
                   max_fix_attempts=max_fix_attempts)
    pr = out["pr"]
    rv = factory.review(pr, journal=j, ask=ctx["ask"])
    urls = _post_review_comments(pr, rv["verdicts"]) if pr["mode"] == "github" else []
    post, green = _retest(pr["diff"], findings[0]["finding_id"], j)
    tests_ok, passed, total = gate.run_tests(j, regression_added=len(findings))
    ready = gate.readiness(pr, green, tests_ok, rv["verdicts"], journal=j)
    metrics = _metrics(ctx, fixed_at=time.time(), tests=f"{passed}/{total}")
    j.emit("metrics", **{k: v for k, v in metrics.items()
                         if k not in ("cost_detail", "tests_passed")})
    summary = _summary(ctx, {**ready, "awaiting": "human", "merged": False}, metrics,
                       rv["verdicts"], blue_status="done")
    summary.update(_remediation(ctx, out, rv, urls, post, green, f"{passed}/{total}"))
    j.write_summary(summary)
    if screenshots:
        _screens(summary, rv["verdicts"])
    return summary


def loop(run_id: str = "demo-run", *, repo: str | None = "Jinstronda/neo-hackathon",
         models: list[str] | None = None, screenshots: bool = True,
         approve: Callable[[list[dict]], bool] | None = None, max_fix_attempts: int = 3,
         agent: str = "swarm", ask: Callable | None = None) -> dict:
    """One run end to end. approve(findings) -> bool asks a human before blue
    touches anything; None approves automatically and records that it did."""
    ctx = start(run_id, models=models, live=True, agent=agent, ask=ask)
    findings = attack(ctx)
    if not findings:
        return _halt(ctx, awaiting=None, blocker="the red swarm proved nothing; no fix to write")
    if approve is not None and not record_approval(ctx, approve(findings)):
        return _halt(ctx, awaiting="fix approval", blocker="a human has not approved the fix")
    return remediate(ctx, repo=repo, screenshots=screenshots, max_fix_attempts=max_fix_attempts)


# Remediation helpers ------------------------------------------------------------

def _checkout(run_id, repo, findings):
    """A fresh clone for the real PR, with a stale branch from a prior run dropped."""
    workdir = RUNS / f".clone-{run_id}"
    _clone(repo, workdir)
    _drop_stale_branch(repo, f"neo/fix-{findings[0]['finding_id']}")
    return workdir


def _clone(repo, dst):
    shutil.rmtree(dst, ignore_errors=True)
    subprocess.run(["gh", "repo", "clone", repo, str(dst), "--", "-q"],
                   check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "jinstronda"], cwd=dst, check=True)
    subprocess.run(["git", "config", "user.email", "joaopanizzutti@gmail.com"], cwd=dst, check=True)
    return dst


def _drop_stale_branch(repo, branch):
    # a throwaway branch from a prior run of this loop; delete so the PR is clean
    subprocess.run(["gh", "api", "--method", "DELETE",
                    f"repos/{repo}/git/refs/heads/{branch}"], capture_output=True, text=True)


def _post_review_comments(pr, verdicts):
    """Post each reviewer's verdict as a real PR comment. Returns the comment URLs."""
    urls = []
    for v in verdicts:
        ev = v.get("recheck_evidence", {})
        body = "\n".join([
            f"### NEO {v['reviewer']} review · vendor: {v['vendor']} · "
            f"**{v['verdict'].upper()}**",
            "",
            v.get("comment", ""),
            "",
            "**Independent recheck (second pass):** re-derived every claim from the diff "
            f"before posting; exploit_still_works=`{ev.get('exploit_still_works')}`.",
            f"> {ev.get('verified', '')}",
            "",
            f"Bound to patch digest `{pr['digest'][:12]}`. A changed diff voids this review.",
        ])
        r = subprocess.run(["gh", "pr", "comment", str(pr["number"]), "--repo", pr["repo"],
                            "--body", body], capture_output=True, text=True)
        url = (r.stdout or "").strip()
        urls.append(url if url.startswith("http") else f"(comment post failed: {r.stderr[:120]})")
    return urls


def _patched_context(diff, root):
    """demo-target with the PR's exact diff applied, in a scratch dir outside the
    repo (inside it, git apply would resolve paths against the real demo-target)."""
    shutil.copytree(REPO / "demo-target", root / "demo-target",
                    ignore=shutil.ignore_patterns("__pycache__"))
    subprocess.run(["git", "apply", "-"], cwd=root, input=diff, text=True, check=True,
                   capture_output=True)
    return root / "demo-target"


def _retest(diff, finding_id, journal):
    """Pre-patch on the vulnerable build, post-patch on a fresh twin of the exact
    reviewed diff. Returns (post_patch_results, post_patch_green)."""
    gate.retest(REPO / "demo-target", phase="pre-patch", journal=journal, finding_id=finding_id)
    with tempfile.TemporaryDirectory(prefix="neo-patched-") as tmp:
        return gate.retest(_patched_context(diff, Path(tmp)), phase="post-patch",
                           journal=journal, finding_id=finding_id)


# run.json --------------------------------------------------------------------

def _cost(ctx):
    """LLM spend of this run only: USAGE is process-wide and watch mode runs many."""
    now, base = llm.usage_summary(), ctx["usage_base"]
    keys = ("calls", "prompt_tokens", "completion_tokens", "est_usd")
    return {**now, **{k: round(now[k] - base[k], 4) for k in keys}}


def _metrics(ctx, *, fixed_at=None, tests=None):
    cost, t0 = _cost(ctx), ctx.get("t_exploit")
    n = len(ctx.get("findings") or [])
    return {
        "minutes_exploit_to_fix": round((fixed_at - t0) / 60, 2) if fixed_at and t0 else None,
        "cost_usd": cost["est_usd"],
        "cost_detail": cost,
        "where": "EU",
        "tested_surface": n,
        "untested_surface": UNTESTED_SURFACE,
        "regression_tests": n if fixed_at else 0,
        "tests_passed": tests,
    }


def _agents(models, verdicts, blue_status):
    out = [{"id": f"neo-{i + 1}", "role": "red", "label": lb, "status": "done"}
           for i, lb in enumerate(red._labels(models))]
    out.append({"id": "blue", "role": "blue", "label": "fixer", "status": blue_status})
    by = {v["reviewer"]: v for v in verdicts}
    for agent_id, role in (("rev-sec", "security"), ("rev-cor", "correctness")):
        out.append({"id": agent_id, "role": "reviewer", "label": role,
                    "status": by.get(role, {}).get("verdict", "pending")})
    return out


def _summary(ctx, merge, metrics, verdicts=(), *, blue_status="pending"):
    """The run.json skeleton. Sections a halted run never reached stay None."""
    keys = ("finding_id", "scenario", "cls", "location", "confirmed_by", "found_by")
    return {
        "id": ctx["id"], "title": "NEO closed-loop run",
        "date": datetime.date.today().isoformat(), "where": "EU",
        "agents": _agents(ctx["models"], verdicts, blue_status),
        "steps": STEPS,
        "metrics": metrics,
        "radar": ctx.get("radar") or {},
        "findings": [{k: f.get(k) for k in keys} for f in ctx.get("findings") or []],
        "approval": ctx.get("approval"),
        "pr": None, "review": None, "retest": None,
        "merge": merge,
        "verification": None,
    }


def _remediation(ctx, out, rv, comment_urls, post, green, tests):
    pr = out["pr"]
    verdict_keys = ("reviewer", "vendor", "verdict", "comment")
    return {
        "pr": {"url": pr["url"], "number": pr["number"], "mode": pr["mode"],
               "branch": pr["branch"], "digest": pr["digest"], "patch_source": out["patch_source"]},
        "review": {"passed": rv["passed"], "comment_urls": comment_urls,
                   "offline": ctx["ask"] is OFFLINE_ASK,
                   "verdicts": [{k: v.get(k) for k in verdict_keys} for v in rv["verdicts"]]},
        "retest": {"post_patch_green": green, "tests": tests, "results": post},
        "verification": out["verification"],
    }


def _halt(ctx, *, awaiting, blocker):
    """End the run before blue, with run.json saying why it stopped."""
    merge = {"ready": False, "blockers": [blocker], "approved_by": [], "awaiting": awaiting,
             "merged": False}
    summary = _summary(ctx, merge, _metrics(ctx))
    ctx["journal"].write_summary(summary)
    return summary


# One evidence panel per step ----------------------------------------------------

def _span(cls, text):
    return f'<span class="{cls}">{shots.esc(text)}</span>'


def _yes(ok):
    return _span("grn" if ok else "red", "yes" if ok else "no")


def _radar_panel(s):
    top = s["radar"]
    pkg = f"{top.get('package')} {top.get('version')}"
    red_labels = " ".join(a["label"] for a in s["agents"] if a["role"] == "red")
    shots.panel("01-radar", "Step 1 · radar: SBOM x KEV x EPSS x OSV", [
        f'{_span("k", "package")}  {_span("w", pkg)}',
        f'{_span("k", "cve")}      {_span("y", top.get("cve"))}   '
        f'{_span("k", "in-KEV")} {_span("red", top.get("kev"))}   '
        f'{_span("k", "epss")} {_span("y", top.get("epss"))}   '
        f'{_span("k", "reachable")} {_span("w", top.get("reachable"))}',
        "",
        _span("dim", "a CVE is a worklist item, not a finding. proof comes next, on the twin."),
        f'{_span("k", "handed to the red swarm ->")} {_span("b", red_labels)}',
    ])


def _red_panel(s):
    lines = [_span("dim", "disposable twin per model · decided server-side from the twin "
                          "event log"), ""]
    for f in s["findings"]:
        by, how = ", ".join(f["found_by"]), f"({f['confirmed_by']})"
        lines.append(f'{_span("red", "[RED]")} {_span("w", f["scenario"])}  '
                     f'{_span("k", f["cls"])} @ {shots.esc(f["location"])}')
        lines.append(f'      {_span("k", "objective_complete=")}{_span("red", "true")}   '
                     f'{_span("k", "found_by")} {_span("b", by)}  {_span("dim", how)}')
    shots.panel("02-red-prepatch", "Step 2 · NEO proves the exploit (pre-patch)", lines)


def _review_panel(s, verdicts):
    pr = s["pr"]
    lines = [f'{_span("k", "PR")} {_span("b", pr["url"])}',
             f'{_span("k", "patch digest")} {_span("dim", pr["digest"][:16])}', ""]
    for v in verdicts:
        ev, vendor = v.get("recheck_evidence", {}), f"({v['vendor']})"
        tone = "grn" if v["verdict"] == "approve" else "red"
        lines.append(f'{_span("w", v["reviewer"])} {_span("dim", vendor)}  '
                     f'{_span(tone, v["verdict"].upper())}')
        lines.append(f'   {_span("k", "recheck exploit_still_works=")}'
                     f'{_span("grn", ev.get("exploit_still_works"))}  '
                     f'{_span("dim", (ev.get("verified") or "")[:90])}')
    shots.panel("04-review", "Step 4 · two-vendor review (each re-runs its claim)", lines)


def _retest_panel(s):
    rt = s["retest"]
    lines = [_span("dim", "fresh twin built from the exact reviewed diff; same exploits "
                          "replayed; server-side verdict"), ""]
    for r in rt["results"]:
        done = r["objective_complete"]
        tone = "red" if done else "grn"
        lines.append(f'{_span(tone, "[RED]" if done else "[GREEN]")} {_span("w", r["scenario"])}'
                     f'  {_span("k", "objective_complete=")}{_span(tone, str(done).lower())}')
    lines += ["", f'{_span("k", "tests")} {_span("grn", rt["tests"] + " passed")}   '
              f'{_span("dim", "(permanent regression + attack replay)")}']
    shots.panel("05-green-postpatch", "Step 5 · twin rebuilt, exploit replayed (post-patch)",
                lines)


def _merge_panel(s):
    m, green = s["merge"], s["retest"]["post_patch_green"]
    ready = _span("grn" if m["ready"] else "red", m["ready"])
    shots.panel("06-merge-ready", "Step 6 · merge gate (a human merges)", [
        f'{_span("k", "exploit dead (server-side)")}  {_yes(green)}',
        f'{_span("k", "tests pass")}                 '
        f'{_yes("tests not passing" not in m["blockers"])}',
        f'{_span("k", "both vendors approve")}       {_yes(len(m["approved_by"]) == 2)} '
        f'{_span("dim", ", ".join(m["approved_by"]))}',
        "",
        f'{_span("w", "ready_to_merge = ")}{ready}   {_span("y", "awaiting a human")}',
        _span("dim", "merge only when the replayed exploit is dead server-side, tests pass, "
                     "and both vendors approve this exact diff."),
    ])


def _screens(summary, verdicts):
    """One evidence PNG per step into screenshots/. Best effort, never fails a run."""
    _radar_panel(summary)
    _red_panel(summary)
    if summary["pr"]["mode"] == "github":
        shots.shot(summary["pr"]["url"], "03-pr")
    _review_panel(summary, verdicts)
    _retest_panel(summary)
    _merge_panel(summary)


if __name__ == "__main__":
    import sys
    loop(sys.argv[1] if len(sys.argv) > 1 else "demo-run")
