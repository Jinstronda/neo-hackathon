"""Real PR route: branch, apply the patch, commit, push over an authenticated remote, then
open the PR through the GitHub REST API. The runner box has no `gh` CLI, so this uses git plus
stdlib urllib and a token (GH_TOKEN/GITHUB_TOKEN). Commits use the clone's own git identity,
set when the clone is created. No force push, no merge: a human merges."""
import json
import os
import subprocess
import urllib.request

API = "https://api.github.com"


def _token():
    tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not tok:
        raise RuntimeError("GH_TOKEN/GITHUB_TOKEN not set for the real PR route")
    return tok


def _run(cmd, cwd, stdin=None):
    out = subprocess.run(cmd, cwd=cwd, input=stdin, text=True, capture_output=True)
    if out.returncode:
        raise RuntimeError(f"{cmd[0]} {cmd[1]} failed: {out.stderr.strip()[:400]}")
    return out.stdout.strip()


def _api(method, path, token, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{API}{path}", data=body, method=method, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "neo-factory"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def open_pr(workdir, repo, base, branch, diff, title, body, commit_msg):
    token = _token()
    remote = f"https://x-access-token:{token}@github.com/{repo}.git"
    _run(["git", "fetch", remote, base], workdir)
    _run(["git", "checkout", "-B", branch, "FETCH_HEAD"], workdir)
    _run(["git", "apply", "--index", "--recount", "-"], workdir, stdin=diff)
    _run(["git", "commit", "-m", commit_msg], workdir)
    _run(["git", "push", remote, f"HEAD:refs/heads/{branch}"], workdir)
    pr = _api("POST", f"/repos/{repo}/pulls", token,
              {"title": title, "head": branch, "base": base, "body": body})
    return pr["html_url"], int(pr["number"])


def merged(repo, number):
    """True only if GitHub says the PR is merged. Who merged is checked by the caller."""
    d = _api("GET", f"/repos/{repo}/pulls/{number}", _token())
    return bool(d.get("merged")), (d.get("merged_by") or {}).get("login")
