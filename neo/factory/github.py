"""Real PR route: branch, apply the patch, commit, push over an authenticated remote, then
open the PR through the GitHub REST API. The runner box has no `gh` CLI, so this uses git plus
stdlib urllib and a token (GH_TOKEN/GITHUB_TOKEN). The token is passed to git through an
http.extraheader in the environment, never on argv, and redacted from any error. Commits use the
clone's own git identity, set when the clone is created. No force push, no merge: a human merges."""
import base64
import json
import os
import subprocess
import urllib.request

API = "https://api.github.com"


def _token():
    tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not tok:  # a dev box logged in with the gh CLI needs no token in .env
        try:
            tok = subprocess.run(["gh", "auth", "token"], capture_output=True,
                                 text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            tok = ""
    if not tok:
        raise RuntimeError("set GH_TOKEN (or log in with `gh auth login`) for the real PR route")
    return tok


def _auth_env(token):
    # GitHub-Actions style: auth travels in an http.extraheader via env, not in the remote URL,
    # so the token never lands on a git command line (visible in `ps`).
    header = "AUTHORIZATION: basic " + base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return {**os.environ, "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
            "GIT_CONFIG_VALUE_0": header}


def _run(cmd, cwd, stdin=None, env=None, secret=None):
    out = subprocess.run(cmd, cwd=cwd, input=stdin, text=True, capture_output=True, env=env)
    if out.returncode:
        err = out.stderr.strip()[:400]
        if secret:
            err = err.replace(secret, "[redacted]")
        raise RuntimeError(f"{cmd[0]} {cmd[1]} failed: {err}")
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
    env = _auth_env(token)
    remote = f"https://github.com/{repo}.git"
    _run(["git", "fetch", remote, base], workdir, env=env, secret=token)
    _run(["git", "checkout", "-B", branch, "FETCH_HEAD"], workdir, secret=token)
    _run(["git", "apply", "--index", "--recount", "-"], workdir, stdin=diff, secret=token)
    _run(["git", "commit", "-m", commit_msg], workdir, secret=token)
    _run(["git", "push", remote, f"HEAD:refs/heads/{branch}"], workdir, env=env, secret=token)
    pr = _api("POST", f"/repos/{repo}/pulls", token,
              {"title": title, "head": branch, "base": base, "body": body})
    return pr["html_url"], int(pr["number"])


def merged(repo, number):
    """True only if GitHub says the PR is merged. Who merged is checked by the caller."""
    d = _api("GET", f"/repos/{repo}/pulls/{number}", _token())
    return bool(d.get("merged")), (d.get("merged_by") or {}).get("login")
