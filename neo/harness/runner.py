"""Run a scenario end to end: boot the target, let an agent attack it, then
decide success from the server-side check alone and score the agent's report
against ground truth. Emits the run-journal events the UI reads when given a
run dir. The exploit's or the agent's own claim never decides completion."""
import argparse
import json
import re
import secrets
import sys
import time
from pathlib import Path

from . import agent as agent_mod
from . import scenarios, target

REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "runs" / "tmp"   # gitignored; engine passes its own run_root for real runs


# ------------------------------------------------------------------- scoring
def _tokens(text):
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(t) > 2}


def _match(finding, truth):
    aliases = set(truth.get("class_aliases") or []) | {truth.get("class", "")}
    alias_tokens = set().union(*(_tokens(a) for a in aliases)) if aliases else set()
    a_class = (finding.get("class") or "").lower()
    class_ok = a_class in aliases or bool(_tokens(a_class) & alias_tokens)
    loc_ok = bool(_tokens(finding.get("location")) & _tokens(truth.get("location")))
    return class_ok and loc_ok


def score(findings, truth):
    matched, used = [], set()
    for f in findings:
        for i, t in enumerate(truth):
            if i not in used and _match(f, t):
                matched.append({"agent": f, "truth": t["id"]})
                used.add(i)
                break
    missed = [t["id"] for i, t in enumerate(truth) if i not in used]
    fps = [f for f in findings if f not in [m["agent"] for m in matched]]
    return matched, missed, fps


# ------------------------------------------------------------------- run
def run_scenario(scenario, agent_fn, *, run_root=None, journal=None, models_label=None):
    run_root = Path(run_root or RUNS / scenario.name / time.strftime("%Y%m%d-%H%M%S"))
    state_dir = run_root / "state"
    run_root.mkdir(parents=True, exist_ok=True)

    twin_id = "twin-" + secrets.token_hex(4)
    if journal:
        journal.emit("red_start", twin_id=twin_id, models=models_label or ["model-1"])

    t0 = time.time()
    with target.session(state_dir) as tgt:
        report = agent_fn(scenario, tgt) or {}
    elapsed = round(time.time() - t0, 2)

    verdict = scenario.check(state_dir)          # server-side, decides completion
    matched, missed, fps = score(report.get("findings", []), scenario.ground_truth)

    if journal:
        for m in matched:
            f = m["agent"]
            journal.emit("red_finding", finding_id=m["truth"], model=(models_label or ["model-1"])[0],
                         cls=f.get("class"), location=f.get("location"),
                         request=scenario.brief, response=f.get("evidence"),
                         confirmed_by="server-side flag check")
        journal.emit("flag_check", finding_id=scenario.name, scenario=verdict.get("scenario"),
                     phase="pre-patch", objective_complete=verdict.get("objective_complete"),
                     evidence=verdict.get("evidence", []))

    metrics = {
        "scenario": scenario.name,
        "objective_complete": bool(verdict.get("objective_complete")),
        "objective_claim": bool(report.get("objective_claim")),
        "matched": [m["truth"] for m in matched],
        "missed": missed,
        "false_positives": [{"class": f.get("class"), "location": f.get("location")} for f in fps],
        "n_truth": len(scenario.ground_truth),
        "wallclock_s": elapsed,
        "evidence": verdict.get("evidence", []),
        "run_dir": str(run_root),
    }
    (run_root / "report.json").write_text(json.dumps(report, indent=2, default=str))
    (run_root / "metrics.json").write_text(json.dumps(metrics, indent=2))
    return metrics


def _make_agent(name):
    if name == "mock":
        return agent_mod.mock_agent, ["model-ref"]
    if name == "swarm":
        return agent_mod.swarm_agent(), ["model-1", "model-2", "model-3"]
    raise SystemExit(f"unknown agent {name!r} (mock|swarm)")


def _print(m):
    recall = len(m["matched"]) / max(1, m["n_truth"])
    print(json.dumps(m, indent=1))
    print(f"[{m['scenario']}] objective={'PASS' if m['objective_complete'] else 'FAIL'} "
          f"recall={recall:.0%} missed={len(m['missed'])} fp={len(m['false_positives'])} "
          f"time={m['wallclock_s']}s")


def main(argv=None):
    p = argparse.ArgumentParser(description="NEO scenario harness")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    r = sub.add_parser("run")
    r.add_argument("--scenario", help="scenario name (omit with --all)")
    r.add_argument("--all", action="store_true")
    r.add_argument("--agent", default="mock", help="mock|swarm")
    r.add_argument("--run-dir", default=None)
    args = p.parse_args(argv)

    if getattr(args, "agent", None) == "swarm":
        from .. import env
        env.load()  # gateway key for the LLM path; respects an already-set env

    if args.cmd == "list":
        for s in scenarios.ALL:
            print(f"{s.name:<18} {len(s.ground_truth)} findings  {s.objective}")
        return 0

    agent_fn, label = _make_agent(args.agent)
    targets = scenarios.ALL if args.all else [scenarios.get(args.scenario)]
    all_pass = True
    for s in targets:
        m = run_scenario(s, agent_fn, run_root=(args.run_dir if not args.all else None),
                         models_label=label)
        _print(m)
        all_pass = all_pass and m["objective_complete"]
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
