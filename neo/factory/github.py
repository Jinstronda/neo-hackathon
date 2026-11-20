"""Real PR route: branch, apply the patch, commit, push, `gh pr create`. Uses the
repo's own git identity. No force push, no merge: a human merges."""
import json
import subprocess


def _run(cmd, cwd, stdin=None):
    out = subprocess.run(cmd, cwd=cwd, input=stdin, text=True, capture_output=True)
    if out.returncode:
        raise RuntimeError(f"{cmd[0]} {cmd[1]} failed: {out.stderr.strip()[:400]}")
    return out.stdout.strip()


def open_pr(workdir, repo, base, branch, diff, title, body, commit_msg):
    _run(["git", "fetch", "origin", base], workdir)
    _run(["git", "checkout", "-b", branch, f"origin/{base}"], workdir)
    _run(["git", "apply", "--index", "-"], workdir, stdin=diff)
    _run(["git", "commit", "-m", commit_msg], workdir)
    _run(["git", "push", "-u", "origin", branch], workdir)
    url = _run(["gh", "pr", "create", "--repo", repo, "--base", base, "--head", branch,
                "--title", title, "--body-file", "-"], workdir, stdin=body)
    return url, int(url.rstrip("/").rsplit("/", 1)[1])


def merged(repo, number):
    """True only if GitHub says the PR is merged. Who merged is checked by the caller."""
    out = _run(["gh", "pr", "view", str(number), "--repo", repo, "--json",
                "state,mergedBy"], None)
    d = json.loads(out)
    return d.get("state") == "MERGED", (d.get("mergedBy") or {}).get("login")
