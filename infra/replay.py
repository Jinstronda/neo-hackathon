"""Exploit replay + the server-side retest gate.

Boots a disposable twin, replays every `exploit_*.py` the red side wrote against
it, then decides success the only way that counts: from the twin's own
server-side event log (checks/check_*.py read $NEO_STATE/events.jsonl). The
exploit script's stdout and exit code never decide the gate.

  pre-patch   we expect at least one objective to complete (red proves a bug).
  post-patch  NO objective may complete, for any scenario. This is the merge
              gate: exit nonzero if any exploit still works.

The contrast between a pre-patch flag_check (objective_complete:true) and the
post-patch one (objective_complete:false) is the gate, per docs/RUN_SCHEMA.md."""
import argparse
import glob
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from . import twin_local

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CONTEXT = REPO / "demo-target"
DEFAULT_CHECKS = REPO / "checks"


def _load_checks(checks_dir):
    """Load every checks/check_*.py and return [(name, check_fn)]. Each check_fn
    takes a state dir and returns {scenario, objective_complete, evidence}."""
    out = []
    for path in sorted(glob.glob(str(Path(checks_dir) / "check_*.py"))):
        name = Path(path).stem
        spec = importlib.util.spec_from_file_location(f"neo_{name}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fn = getattr(mod, "check", None)
        if fn:
            out.append((name, fn))
    return out


def find_exploits(context) -> list[str]:
    return sorted(glob.glob(str(Path(context) / "exploit_*.py")))


def run_exploit(script: str, base_url: str, timeout: float = 90) -> tuple[str, int]:
    """Run one exploit against the twin so the app logs events. The output is
    kept as evidence only; it does not decide the gate."""
    try:
        proc = subprocess.run(
            [sys.executable, script, base_url],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(Path(script).parent),  # exploits import sibling _http
        )
        return (proc.stdout or "") + (proc.stderr or ""), proc.returncode
    except subprocess.TimeoutExpired:
        return "exploit timed out", 124


def replay(context=DEFAULT_CONTEXT, checks=DEFAULT_CHECKS, phase="post-patch",
           health=twin_local.DEFAULT_HEALTH, container_port=twin_local.DEFAULT_PORT,
           dockerfile=twin_local.DEFAULT_DOCKERFILE, emit=print) -> tuple[list[dict], bool]:
    """Build a fresh twin, replay all exploits, verdict from the event log.
    Returns (results, gate_pass)."""
    exploits = find_exploits(context)
    check_fns = _load_checks(checks)
    if not exploits or not check_fns:
        # ponytail: vacuous pass until the red side lands exploit_*.py and a
        # matching check. pytest still gates in CI; becomes real on first pair.
        emit(json.dumps({"type": "retest", "note": "no exploits/checks to replay yet",
                         "phase": phase, "status": "green"}))
        return [], True

    twin = twin_local.up(context, health=health, container_port=container_port,
                         dockerfile=dockerfile)
    emit(json.dumps({"type": "twin_deploy", **twin.event(), "phase": phase}))
    try:
        # drive every exploit against the one twin; events accumulate in /state
        for script in exploits:
            output, code = run_exploit(script, twin.base_url)
            emit(json.dumps({"type": "exploit_run", "exploit": Path(script).stem,
                             "exit": code, "tail": output[-200:]}))
        # server-side verdict: read the twin's own event log via checks/
        results = []
        for name, fn in check_fns:
            r = fn(str(twin.state_dir))
            done = bool(r.get("objective_complete"))
            scenario = r.get("scenario", name)
            results.append({"check": name, "scenario": scenario,
                            "objective_complete": done})
            emit(json.dumps({"type": "flag_check", "finding_id": scenario,
                             "scenario": scenario, "phase": phase,
                             "objective_complete": done,
                             "evidence": r.get("evidence", [])}))
    finally:
        twin_local.teardown(twin)

    any_complete = any(r["objective_complete"] for r in results)
    if phase == "post-patch":
        gate_pass = not any_complete        # merge gate: every objective must fail
        status = "green" if gate_pass else "red"
    else:
        gate_pass = any_complete            # pre-patch: at least one must land
        status = "red" if any_complete else "green"
    for r in results:
        emit(json.dumps({"type": "retest", "finding_id": r["scenario"],
                         "scenario": r["scenario"], "phase": phase,
                         "objective_complete": r["objective_complete"],
                         "status": "red" if r["objective_complete"] else "green"}))
    emit(json.dumps({"type": "retest_summary", "phase": phase, "status": status,
                     "gate_pass": gate_pass}))
    return results, gate_pass


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="NEO exploit replay / retest gate")
    p.add_argument("--context", default=str(DEFAULT_CONTEXT))
    p.add_argument("--checks", default=str(DEFAULT_CHECKS))
    p.add_argument("--phase", choices=["pre-patch", "post-patch"], default="post-patch")
    p.add_argument("--health", default=twin_local.DEFAULT_HEALTH)
    p.add_argument("--port", type=int, default=twin_local.DEFAULT_PORT)
    p.add_argument("--dockerfile", default=str(twin_local.DEFAULT_DOCKERFILE))
    args = p.parse_args(argv)
    _, gate_pass = replay(args.context, args.checks, phase=args.phase,
                          health=args.health, container_port=args.port,
                          dockerfile=args.dockerfile)
    if args.phase == "post-patch" and not gate_pass:
        print("RETEST FAILED: an exploit still works; PR cannot merge", file=sys.stderr)
        return 1
    if args.phase == "pre-patch" and not gate_pass:
        print("PRE-PATCH: no exploit landed; nothing to prove", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
