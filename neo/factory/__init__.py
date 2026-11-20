"""The fix factory: the blue side's PR lifecycle.

    pr = factory.open_pr(finding, patch, journal=j)        # branch + patch + evidence
    rv = factory.review(pr, journal=j)                     # two vendors, each rechecks
    factory.ready_to_merge(pr, retest_green, tests_pass, rv["verdicts"])
    factory.release(pr, {"by": "human", "user": "..."}, ...)  # after a human merges

Readiness is bound to the exact diff (sha256). Any change to the patch voids the
reviews. The factory never merges; it refuses "ready" unless the replayed exploit
is dead (server-side flag check), tests pass and both reviewers approve."""
import datetime
import hashlib
import json
from pathlib import Path

from .. import reviewers
from . import github

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / "runs" / "prs"
REGRESSIONS = ROOT / "runs" / "regressions.jsonl"
ROLES = tuple(reviewers.REVIEWERS)


def _digest(diff):
    return hashlib.sha256(diff.encode()).hexdigest()


def _evidence_body(finding, digest):
    checks = finding.get("flag_check") or {}
    return "\n".join([
        f"## Fix: {finding.get('cls')} at {finding.get('location')}",
        "",
        f"Finding `{finding.get('finding_id')}` was proven on a disposable twin. The "
        "server-side flag check went red before this patch.",
        "",
        "### Exploit request",
        "```", str(finding.get("request", "")), "```",
        "### Server-side flag check (pre-patch)",
        "```json", json.dumps(checks, indent=1), "```",
        "### Merge rule",
        "Merge only when the same exploit replays against a fresh patched twin, the flag "
        "check stays green, the tests pass, and both reviewers approve this exact diff.",
        "",
        f"Patch digest: `{digest}`",
    ])


def open_pr(finding, patch, *, journal=None, repo=None, workdir=None, base="main", store=STORE):
    """Open a PR for a patch. With repo+workdir it is a real GitHub PR; otherwise a
    local PR record under runs/prs (demo and offline runs)."""
    fid = finding.get("finding_id", "finding")
    digest = _digest(patch)
    branch = f"neo/fix-{fid}"
    title = f"fix: close {finding.get('cls', 'finding')} at {finding.get('location', '?')}"
    body = _evidence_body(finding, digest)
    if repo and workdir:
        url, number = github.open_pr(workdir, repo, base, branch, patch, title, body, title)
        mode = "github"
    else:
        store = Path(store)
        store.mkdir(parents=True, exist_ok=True)
        number = len(list(store.glob("*.json"))) + 1
        url, mode = f"local://pr/{number}", "local"
    pr = {"number": number, "url": url, "mode": mode, "repo": repo, "branch": branch,
          "base": base, "title": title, "body": body, "diff": patch, "digest": digest,
          "finding": finding, "date": datetime.date.today().isoformat(), "status": "open"}
    if mode == "local":
        (Path(store) / f"{number}.json").write_text(json.dumps(pr, indent=1))
    if journal:
        journal.emit("blue_patch", finding_id=fid, pr_url=url, pr_number=number,
                     branch=branch, diff=patch, digest=digest,
                     commits=[{"msg": title, "kind": "code"}])
    return pr


def review(pr, *, guidelines="", journal=None, ask=None):
    """Both reviewers, each with its own recheck. {verdicts, passed, disagreement}."""
    kw = {"ask": ask} if ask else {}
    return reviewers.review_pr(pr, guidelines=guidelines, journal=journal, **kw)


def blockers(pr, retest_green, tests_pass, verdicts):
    """Every reason the PR may not merge. Empty list means ready."""
    out = []
    if retest_green is not True:
        out.append("retest not green: the exploit is not proven dead on the patched twin")
    if tests_pass is not True:
        out.append("tests not passing")
    by_role = {v.get("reviewer"): v for v in verdicts or []}
    for role in ROLES:
        v = by_role.get(role)
        if not v:
            out.append(f"{role} review missing")
        elif v.get("pr_digest") != pr["digest"]:
            out.append(f"{role} review is for a different diff")
        elif not v.get("rechecked"):
            out.append(f"{role} review was not rechecked")
        elif v.get("verdict") != "approve":
            out.append(f"{role} reviewer requested changes")
    return out


def ready_to_merge(pr, retest_green, tests_pass, verdicts):
    return not blockers(pr, retest_green, tests_pass, verdicts)


def release(pr, merge_signal, *, retest_green, tests_pass, verdicts, journal=None,
            regressions=REGRESSIONS):
    """Run after a human merges. Re-checks the gate, then records the fixed bug as a
    permanent regression test plus attack replay that CI runs on every push."""
    if (merge_signal or {}).get("by") != "human":
        raise PermissionError("release needs a human merge signal")
    gate = blockers(pr, retest_green, tests_pass, verdicts)
    if gate:
        raise PermissionError(f"merge gate not met: {gate}")
    if pr["mode"] == "github":
        is_merged, login = github.merged(pr["repo"], pr["number"])
        if not is_merged:
            raise PermissionError("GitHub does not show the PR as merged")
        merge_signal = {**merge_signal, "user": login}
    f = pr["finding"]
    regression = {"finding_id": f.get("finding_id"), "scenario": f.get("scenario"),
                  "cls": f.get("cls"), "location": f.get("location"),
                  "exploit": f.get("exploit"), "check": f.get("check"),
                  "pr_number": pr["number"], "digest": pr["digest"],
                  "date": datetime.date.today().isoformat()}
    regressions = Path(regressions)
    regressions.parent.mkdir(parents=True, exist_ok=True)
    with regressions.open("a") as fh:
        fh.write(json.dumps(regression) + "\n")
    approved_by = [f"{v['reviewer']}:{v['vendor']}" for v in verdicts]
    if journal:
        journal.emit("merge", pr_number=pr["number"], by="human",
                     user=merge_signal.get("user"), approved_by=approved_by)
        journal.emit("release", pr_number=pr["number"], digest=pr["digest"],
                     regression=regression)
    return {"status": "released", "pr_number": pr["number"], "approved_by": approved_by,
            "regression": regression}


def demo():
    import tempfile
    from ..journal import Journal

    tmp = Path(tempfile.mkdtemp())
    j = Journal(tmp / "run")
    finding = {"finding_id": "f-sqli-1", "cls": "sql-injection", "location": "POST /login",
               "scenario": "sql-injection", "request": "username=admin' --&password=x",
               "exploit": "demo-target/exploit_sqli.py", "check": "checks/check_sqli.py",
               "flag_check": {"objective_complete": True}}
    pr = open_pr(finding, reviewers.DEMO_DIFF, journal=j, store=tmp / "prs")
    assert pr["mode"] == "local" and pr["number"] == 1 and "Claude" not in pr["body"]

    def ok(v):
        return {"reviewer": v, "vendor": "x", "verdict": "approve", "rechecked": True,
                "pr_digest": pr["digest"]}
    good = [ok("security"), ok("correctness")]
    assert ready_to_merge(pr, True, True, good)
    assert not ready_to_merge(pr, False, True, good)          # exploit still alive
    assert not ready_to_merge(pr, True, False, good)          # tests red
    assert not ready_to_merge(pr, True, True, good[:1])       # one reviewer only
    assert not ready_to_merge(pr, True, True, [ok("security"), {**ok("correctness"),
                              "verdict": "request_changes"}])
    assert not ready_to_merge(pr, True, True, [ok("security"), {**ok("correctness"),
                              "pr_digest": "other"}])         # review of an older diff
    assert not ready_to_merge(pr, True, True, [ok("security"), {**ok("correctness"),
                              "rechecked": False}])
    try:
        release(pr, {"by": "agent"}, retest_green=True, tests_pass=True, verdicts=good)
        raise AssertionError("agent merge accepted")
    except PermissionError:
        pass
    try:
        release(pr, {"by": "human"}, retest_green=False, tests_pass=True, verdicts=good)
        raise AssertionError("release with live exploit accepted")
    except PermissionError:
        pass
    r = release(pr, {"by": "human", "user": "reviewer"}, retest_green=True, tests_pass=True,
                verdicts=good, journal=j, regressions=tmp / "regressions.jsonl")
    assert r["status"] == "released"
    assert [e["type"] for e in j.events] == ["blue_patch", "merge", "release"]
    print("factory self-check: ok")


if __name__ == "__main__":
    demo()
