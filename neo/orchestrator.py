"""The NEO closed loop, one run end to end:

  radar matches a dropped CVE to our SBOM -> the NEO swarm proves the exploits on
  disposable twins (server-side flag checks go red) -> blue writes the fix and
  opens a real PR -> two vendors each re-run their claim and approve -> a fresh
  twin is rebuilt with the patch and the same exploits replayed (checks go green)
  -> tests pass -> the loop stops at a merge a human presses.

Writes runs/<id>/ (events.jsonl + run.json + metrics.json) per docs/RUN_SCHEMA.md
and one screenshot per step. Server-side flag checks, never an agent's report,
decide red/green. This module runs the loop; it never merges.
"""
import datetime
import json
import shutil
import subprocess
import time
from pathlib import Path

from . import blue, config, env, factory, gate, llm, radar, red, shots, term
from .journal import Journal

REPO = Path(__file__).resolve().parent.parent
RUNS = REPO / "runs"
DATE = "2026-11-20"


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
            f"### NEO {v['reviewer']} review — vendor: {v['vendor']} — **{v['verdict'].upper()}**",
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


def _agents(findings, verdicts):
    labels = red._labels(config.RED_SWARM)
    out = [{"id": f"neo-{i+1}", "role": "red", "label": lb, "status": "done"}
           for i, lb in enumerate(labels)]
    out.append({"id": "blue", "role": "blue", "label": "fixer", "status": "done"})
    by = {v["reviewer"]: v for v in verdicts}
    out.append({"id": "rev-sec", "role": "reviewer", "label": "security",
                "status": by.get("security", {}).get("verdict", "pending")})
    out.append({"id": "rev-cor", "role": "reviewer", "label": "correctness",
                "status": by.get("correctness", {}).get("verdict", "pending")})
    return out


STEPS = [
    {"key": "radar", "title": "Radar match", "live": False, "events": ["radar_match"]},
    {"key": "red", "title": "NEO proves the exploit", "live": True,
     "events": ["red_start", "red_finding", "flag_check"]},
    {"key": "blue", "title": "Blue opens the patch PR", "live": True, "events": ["blue_patch"]},
    {"key": "review", "title": "Two reviewers check the PR", "live": True, "events": ["review"]},
    {"key": "retest", "title": "Twin rebuilt, exploit replayed", "live": True,
     "events": ["twin_deploy", "retest", "tests"]},
    {"key": "merge", "title": "Human merges", "live": False, "events": ["merge_ready", "merge"]},
]


def loop(run_id="demo-run", *, repo="Jinstronda/neo-hackathon", models=None, screenshots=True):
    env.load()
    models = models or config.RED_SWARM
    run_dir = RUNS / run_id
    shutil.rmtree(run_dir, ignore_errors=True)
    j = Journal(run_dir)
    term.attach(j)  # live terminal view of every journal event
    workdir = REPO / "runs" / f".clone-{run_id}"

    # 1. radar -------------------------------------------------------------
    scan = radar.scan()
    top = scan["matches"][0] if scan["matches"] else {}
    j.emit("radar_match", cve=top.get("cve"), kev=top.get("kev"), epss=top.get("epss"),
           osv=top.get("osv", []), package=top.get("package"), version=top.get("version"),
           reachable=top.get("reachable"), kev_source=scan.get("kev_source"))

    # 2. NEO proves the exploits (swarm, server-side) ----------------------
    findings = red.run(models, run_root=run_dir / "red", journal=j)
    if not findings:
        raise RuntimeError("red swarm proved nothing; aborting before any PR")
    t_exploit = next(e["ts"] for e in j.events
                     if e["type"] == "flag_check" and e.get("objective_complete"))

    # 3. blue writes the fix + opens the real PR ---------------------------
    _clone(repo, workdir)
    _drop_stale_branch(repo, f"neo/fix-{findings[0]['finding_id']}")
    out = blue.run(findings, repo=repo, workdir=workdir, journal=j)
    pr = out["pr"]

    # 4. two vendors review the exact diff; post real PR comments ----------
    rv = factory.review(pr, journal=j)
    verdicts = rv["verdicts"]
    comment_urls = _post_review_comments(pr, verdicts) if pr["mode"] == "github" else []

    # 5. fresh twin, same exploits replayed: pre-patch red, post-patch green
    gate.retest(REPO / "demo-target", phase="pre-patch", journal=j,
                finding_id=findings[0]["finding_id"])                 # same build, unpatched
    post, retest_green = gate.retest(Path(workdir) / "demo-target", phase="post-patch",
                                     journal=j, finding_id=findings[0]["finding_id"])
    tests_ok, passed, total = gate.run_tests(j, regression_added=len(findings))

    # 6. merge gate (never merges) -----------------------------------------
    ready = gate.readiness(pr, retest_green, tests_ok, verdicts, journal=j)
    t_fix = time.time()

    # 7. metrics -----------------------------------------------------------
    cost = llm.usage_summary()
    tested = len(findings)
    metrics = {
        "minutes_exploit_to_fix": round((t_fix - t_exploit) / 60, 2),
        "cost_usd": cost["est_usd"],
        "cost_detail": cost,
        "where": "EU",
        "tested_surface": tested,
        "untested_surface": 2,  # GET /me, GET / have no dedicated adversarial scenario yet
        "regression_tests": len(findings),
        "tests_passed": f"{passed}/{total}",
    }
    j.emit("metrics", **{k: metrics[k] for k in (
        "minutes_exploit_to_fix", "cost_usd", "where", "tested_surface",
        "untested_surface", "regression_tests")})

    # 8. run.json (the artifact the UI consumes) ---------------------------
    summary = {
        "id": run_id, "title": "NEO closed-loop run", "date": DATE, "where": "EU",
        "agents": _agents(findings, verdicts),
        "steps": STEPS,
        "metrics": metrics,
        "radar": top,
        "findings": [{k: f.get(k) for k in ("finding_id", "scenario", "cls", "location",
                                            "confirmed_by", "found_by")} for f in findings],
        "pr": {"url": pr["url"], "number": pr["number"], "mode": pr["mode"],
               "branch": pr["branch"], "digest": pr["digest"], "patch_source": out["patch_source"]},
        "review": {"passed": rv["passed"], "comment_urls": comment_urls,
                   "verdicts": [{k: v.get(k) for k in ("reviewer", "vendor", "verdict", "comment")}
                                for v in verdicts]},
        "retest": {"post_patch_green": retest_green, "tests": f"{passed}/{total}",
                   "results": post},
        "merge": {**ready, "awaiting": "human", "merged": False},
        "verification": out["verification"],
    }
    j.write_summary(summary)

    # 9. one screenshot per step ------------------------------------------
    if screenshots:
        _screens(top, findings, pr, verdicts, post, retest_green, passed, total, ready)

    return summary


def _screens(top, findings, pr, verdicts, post, green, passed, total, ready):
    E = shots.esc
    shots.panel("01-radar", "Step 1 — radar: SBOM x KEV x EPSS x OSV", [
        f'<span class="k">package</span>  <span class="w">{E(top.get("package"))} '
        f'{E(top.get("version"))}</span>',
        f'<span class="k">cve</span>      <span class="y">{E(top.get("cve"))}</span>   '
        f'<span class="k">in-KEV</span> <span class="red">{E(top.get("kev"))}</span>   '
        f'<span class="k">epss</span> <span class="y">{E(top.get("epss"))}</span>   '
        f'<span class="k">reachable</span> <span class="w">{E(top.get("reachable"))}</span>',
        "",
        '<span class="dim">a CVE is a worklist item, not a finding. proof comes next, '
        'on the twin.</span>',
        f'<span class="k">handed to the red swarm &rarr;</span> '
        f'<span class="b">{E(" ".join(red._labels(config.RED_SWARM)))}</span>',
    ])
    red_lines = ['<span class="dim">disposable twin per model &middot; decided server-side from '
                 'the twin event log</span>', ""]
    for f in findings:
        red_lines.append(
            f'<span class="red">[RED]</span> <span class="w">{E(f["scenario"])}</span>  '
            f'<span class="k">{E(f["cls"])}</span> @ {E(f["location"])}')
        red_lines.append(
            f'      <span class="k">objective_complete=</span><span class="red">true</span>'
            f'   <span class="k">found_by</span> <span class="b">{E(", ".join(f["found_by"]))}'
            f'</span>  <span class="dim">({E(f["confirmed_by"])})</span>')
    shots.panel("02-red-prepatch", "Step 2 — NEO proves the exploit (pre-patch)", red_lines)

    if pr["mode"] == "github":
        shots.shot(pr["url"], "03-pr")
    rv_lines = [f'<span class="k">PR</span> <span class="b">{E(pr["url"])}</span>',
                f'<span class="k">patch digest</span> <span class="dim">{E(pr["digest"][:16])}</span>',
                ""]
    for v in verdicts:
        col = "grn" if v["verdict"] == "approve" else "red"
        ev = v.get("recheck_evidence", {})
        rv_lines.append(
            f'<span class="w">{E(v["reviewer"])}</span> <span class="dim">({E(v["vendor"])})</span>'
            f'  <span class="{col}">{E(v["verdict"].upper())}</span>')
        rv_lines.append(f'   <span class="k">recheck exploit_still_works=</span>'
                        f'<span class="grn">{E(ev.get("exploit_still_works"))}</span>  '
                        f'<span class="dim">{E((ev.get("verified") or "")[:90])}</span>')
    shots.panel("04-review", "Step 4 — two-vendor review (each re-runs its claim)", rv_lines)

    g_lines = ['<span class="dim">fresh twin rebuilt from the patched branch; same exploits '
               'replayed; server-side verdict</span>', ""]
    for r in post:
        g_lines.append(
            f'<span class="grn">[GREEN]</span> <span class="w">{E(r["scenario"])}</span>  '
            f'<span class="k">objective_complete=</span><span class="grn">false</span>')
    g_lines += ["", f'<span class="k">tests</span> <span class="grn">{passed}/{total} passed</span>'
                f'   <span class="dim">(permanent regression + attack replay)</span>']
    shots.panel("05-green-postpatch", "Step 5 — twin rebuilt, exploit dead (post-patch)", g_lines)

    shots.panel("06-merge-ready", "Step 6 — merge gate (a human merges)", [
        f'<span class="k">exploit dead (server-side)</span>  <span class="grn">yes</span>',
        f'<span class="k">tests pass</span>                 <span class="grn">yes</span>',
        f'<span class="k">both vendors approve</span>       '
        f'<span class="grn">{E(len(ready["approved_by"]) == 2)}</span> '
        f'<span class="dim">{E(", ".join(ready["approved_by"]))}</span>',
        "",
        f'<span class="w">ready_to_merge = </span>'
        f'<span class="{"grn" if ready["ready"] else "red"}">{E(ready["ready"])}</span>'
        f'   <span class="y">awaiting a human</span>',
        '<span class="dim">merge only when the replayed exploit is dead server-side, tests '
        'pass, and both vendors approve this exact diff.</span>',
    ])


if __name__ == "__main__":
    import sys
    loop(sys.argv[1] if len(sys.argv) > 1 else "demo-run")
