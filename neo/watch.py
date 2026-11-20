"""Neo attacks your server 24/7. Every interval the radar rescans the SBOM against
the live KEV feed, and each KEV match it has not seen before triggers one full
loop: red proves, blue fixes, two vendors review, a fresh twin replays, a human
merges.

  state    runs/watch/state.json    seen matches, cve|package|version -> run id
  journal  runs/watch/events.jsonl  watch_tick, watch_trigger, watch_error

A run that raises is journaled and its match stays unseen, so the next cycle
retries it; the daemon keeps going. --once runs one cycle, for cron and CI.
"""
import argparse
import datetime
import json
import os
import sys
import time
from pathlib import Path

from . import config, radar, term
from .journal import Journal

ROOT = Path(__file__).resolve().parent.parent / "runs" / "watch"
INTERVAL = 6 * 3600


def _loop(**kw) -> dict:
    from . import orchestrator  # lazy: `neo watch --help` and the tests skip the whole loop
    return orchestrator.loop(**kw)


def _key(m: dict) -> str:
    return f"{m['cve']}|{m['package']}|{m['version']}"


def _error(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"[:300]


def load_state(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {"cycle": 0, "seen": {}}


def save_state(path: Path, state: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(path)  # atomic: a Ctrl-C mid-write never loses the seen-set


def _trigger(m: dict, run_id: str, journal: Journal, *, run_loop, repo) -> bool:
    journal.emit("watch_trigger", cve=m["cve"], package=m["package"],
                 version=m["version"], run_id=run_id)
    try:
        run_loop(run_id=run_id, repo=repo, screenshots=False)
    except Exception as e:  # noqa: BLE001 - one failed run must not stop the watch
        journal.emit("watch_error", run_id=run_id, cve=m["cve"], error=_error(e))
        return False
    return True


def cycle(state: dict, path: Path, journal: Journal, *, scan, run_loop, repo,
          next_in_s: int) -> tuple[int, int]:
    """One radar pass. Runs the loop once per new KEV match. Returns (triggered, errors)."""
    state["cycle"] += 1
    try:
        result = scan()
    except Exception as e:  # noqa: BLE001 - a bad feed day must not stop the watch
        journal.emit("watch_error", cycle=state["cycle"], error=_error(e))
        return 0, 1
    new = [m for m in result["matches"] if m.get("kev") and _key(m) not in state["seen"]]
    journal.emit("watch_tick", cycle=state["cycle"], new_matches=len(new),
                 kev_source=result.get("kev_source"), next_in_s=next_in_s)
    stamp, used, errors = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d%H%M"), set(), 0
    for m in new:
        run_id = f"watch-{m['cve']}-{stamp}"
        if run_id in used:  # same CVE in two packages: the loop wipes runs/<id>/, keep both
            run_id += f"-{m['package'].lower()}"
        used.add(run_id)
        if _trigger(m, run_id, journal, run_loop=run_loop, repo=repo):
            state["seen"][_key(m)] = run_id
            save_state(path, state)  # per run, so a Ctrl-C mid-cycle never reruns it
        else:
            errors += 1
    return len(new), errors


def watch(*, interval: int = INTERVAL, once: bool = False, repo: str | None = None,
          scan=radar.scan, run_loop=_loop, root: Path = ROOT, sleep=time.sleep,
          live: bool = True) -> dict:
    """Scan, trigger, sleep, until Ctrl-C (or one cycle with once). Returns the tally."""
    journal = Journal(root)
    if live:
        term.attach(journal)
    path = root / "state.json"
    state = load_state(path)
    stats = {"cycles": 0, "triggered": 0, "errors": 0, "stopped": False}
    try:
        while True:
            t, e = cycle(state, path, journal, scan=scan, run_loop=run_loop, repo=repo,
                         next_in_s=0 if once else interval)
            save_state(path, state)
            stats["cycles"] += 1
            stats["triggered"] += t
            stats["errors"] += e
            if once:
                break
            sleep(interval)
    except KeyboardInterrupt:
        stats["stopped"] = True
    return stats


def _positive(s: str) -> int:
    n = int(s)
    if n < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return n


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="neo watch", description="Neo attacks your server 24/7: rescan the KEV feed "
        "every interval and run the full loop on each new match.")
    p.add_argument("--interval", type=_positive, default=INTERVAL, metavar="SECONDS",
                   help="seconds between scans (default: %(default)s, six hours)")
    p.add_argument("--once", action="store_true", help="run one cycle and exit (cron, CI)")
    p.add_argument("--local", action="store_true",
                   help="record PRs locally and never touch GitHub")
    a = p.parse_args(argv)
    try:
        config.swarm()
    except RuntimeError as e:
        raise SystemExit(f"neo watch: {e}") from None
    repo = None if a.local else config.GITHUB_REPO
    state = os.path.relpath(ROOT / "state.json")
    print(f"neo watch: every {a.interval}s, PRs to {repo or 'a local record'}, state {state}")
    s = watch(interval=a.interval, once=a.once, repo=repo)
    print(f"neo watch: {'stopped' if s['stopped'] else 'done'} after {s['cycles']} cycle(s), "
          f"{s['triggered']} run(s) triggered, {s['errors']} error(s); state {state}")
    return 1 if s["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
