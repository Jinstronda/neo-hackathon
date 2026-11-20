"""The NEO red swarm. Each open-weight model in config.RED_SWARM runs in its own
context, drives the harness against its own fresh disposable target, and tries to
make the server-side flag check fire. A finding counts only when the server-side
check confirms it OR a second model reproduces the same class, never on a model's
own say-so. Which model found what is recorded.

Public UI shows the models as model-1..model-n; their names stay in config. The
reasoning (plan, judge) runs on the open-weight models through neo/llm.py; the
attack itself is a vetted reference primitive, so a model reasons about the
target but cannot run arbitrary code against it.

Methodology this enforces:
  neo/skills/breachbench/SKILL.md     server-side evidence decides, not the model;
                                      a class counts only on confirm or reproduction.
  neo/skills/adversary-review/SKILL.md grade demonstrated impact, never potential;
                                      the severity gate before any report line.
"""
import time
from collections.abc import Callable
from pathlib import Path

from . import config
from .harness import agent as agent_mod
from .harness import scenarios, target
from .journal import Journal

# scenario name -> (exploit script, server-side check) for the PR evidence and
# the permanent regression record.
_ARTIFACTS = {
    "sql-injection": ("demo-target/exploit_sqli.py", "checks/check_sqli.py"),
    "ssrf-metadata": ("demo-target/exploit_ssrf.py", "checks/check_ssrf.py"),
    "weak-jwt-secret": ("demo-target/exploit_jwt.py", "checks/check_jwt.py"),
}


def _labels(models):
    return [f"model-{i + 1}" for i in range(len(models))]


def _class_of(report, scenario):
    """The classes a model's judge actually reported, lowercased."""
    aliases = set()
    for gt in scenario.ground_truth:
        aliases |= {a.lower() for a in gt.get("class_aliases", [])} | {gt["class"].lower()}
    hit = set()
    for f in report.get("findings", []):
        c = (f.get("class") or "").lower()
        if c in aliases or any(a in c or c in a for a in aliases if c):
            hit.add(c or "?")
    return hit


def prove(scenario: scenarios.Scenario, models: list[str] | None = None, *, run_root: Path,
          labels: list[str] | None = None, journal: Journal | None = None,
          agent_factory: Callable = agent_mod.swarm_agent) -> dict | None:
    """Run every red model against its own fresh target for one scenario. Returns a
    finding dict when the objective is confirmed (server-side, or two models), else
    None. agent_factory(model_list) -> agent_fn lets the self-check inject a
    deterministic driver."""
    models = models or config.RED_SWARM
    labels = labels or _labels(models)

    attempts = []  # one per model: who, did the server-side check fire, what it claimed
    server_verdict = None
    for model, label in zip(models, labels, strict=True):
        state_dir = run_root / scenario.name / f"{label}-state"
        agent_fn = agent_factory([model])  # this model plans AND judges, in its own context
        fallback = False
        with target.session(state_dir) as tgt:
            try:
                report = agent_fn(scenario, tgt) or {}
            except Exception as e:  # noqa: BLE001 - reasoning layer failed, still probe
                # the model's plan/judge errored; probe with the vetted reference chain so
                # the server-side check can still rule, and record that it was a fallback.
                try:
                    scenario.exploit(tgt)
                except Exception:  # noqa: BLE001
                    pass
                report = {"error": type(e).__name__, "findings": [], "fallback": "reference-chain"}
                fallback = True
        verdict = scenario.check(str(state_dir))  # server-side, decides completion
        landed = bool(verdict.get("objective_complete"))
        attempts.append({"model": model, "label": label, "landed": landed,
                         "classes": sorted(_class_of(report, scenario)),
                         "error": report.get("error"), "fallback": fallback})
        if landed and server_verdict is None:
            server_verdict = verdict

    confirmed_server = [a for a in attempts if a["landed"]]
    reproduced = [a for a in attempts if a["classes"]]
    # the rule: server-side check confirms, OR a second model reproduces the class
    if not confirmed_server and len(reproduced) < 2:
        return None

    gt = scenario.ground_truth[0]
    exploit, check = _ARTIFACTS[scenario.name]
    found_by = [a["label"] for a in (confirmed_server or reproduced)]
    verdict = server_verdict or scenario.check(
        str(run_root / scenario.name / f"{labels[0]}-state"))
    finding = {
        "finding_id": gt["id"],
        "scenario": scenario.name,
        "cls": gt["class"],
        "location": gt["location"],
        "request": scenario.brief,
        "response": verdict.get("evidence", []),
        "exploit": exploit,
        "check": check,
        "confirmed_by": "server-side flag check" if confirmed_server else "two-model reproduction",
        "found_by": found_by,
        "flag_check": verdict,
        "attempts": attempts,
    }
    if journal:
        primary = (confirmed_server or reproduced)[0]
        journal.emit("red_finding", finding_id=gt["id"], model=primary["label"],
                     cls=gt["class"], location=gt["location"], request=scenario.brief,
                     response=verdict.get("evidence", []),
                     confirmed_by=finding["confirmed_by"], found_by=found_by)
        journal.emit("flag_check", finding_id=scenario.name, scenario=scenario.name,
                     phase="pre-patch", objective_complete=bool(verdict.get("objective_complete")),
                     evidence=verdict.get("evidence", []))
    return finding


def run(models: list[str] | None = None, scenarios_: list[scenarios.Scenario] | None = None, *,
        run_root: Path, journal: Journal | None = None,
        agent_factory: Callable = agent_mod.swarm_agent) -> list[dict]:
    """Drive the whole red phase. Emits one red_start, then per scenario a
    red_finding and a pre-patch flag_check. Returns the confirmed findings, which
    blue consumes."""
    models = models or config.RED_SWARM
    scenarios_ = scenarios_ or scenarios.ALL
    labels = _labels(models)
    twin_id = "twin-red-" + hex(int(time.time()))[-8:]
    if journal:
        journal.emit("red_start", twin_id=twin_id, models=labels)
    findings = []
    for s in scenarios_:
        f = prove(s, models, run_root=run_root, labels=labels, journal=journal,
                  agent_factory=agent_factory)
        if f:
            findings.append(f)
    return findings


def demo():
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    j = Journal(tmp / "run")

    def factory(_models):
        # deterministic driver: ignore the model list, run the vetted reference chain
        return agent_mod.mock_agent

    findings = run(models=["m-a", "m-b"], run_root=tmp / "state", journal=j,
                   agent_factory=factory)
    assert len(findings) == 3, findings
    assert {f["scenario"] for f in findings} == {
        "sql-injection", "ssrf-metadata", "weak-jwt-secret"}
    assert all(f["flag_check"]["objective_complete"] for f in findings)
    assert all(f["confirmed_by"] == "server-side flag check" for f in findings)
    types = [e["type"] for e in j.events]
    assert types[0] == "red_start"
    assert types.count("red_finding") == 3 and types.count("flag_check") == 3
    assert all(e["phase"] == "pre-patch" for e in j.events if e["type"] == "flag_check")
    print("red self-check: ok (3 findings, all server-side confirmed)")


if __name__ == "__main__":
    demo()
