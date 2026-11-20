"""Agents that drive a scenario. An agent takes (scenario, target) and returns a
report `{objective_claim, findings, chain}`. The server-side check, not this
report, decides whether the objective was met.

Two agents:
  mock_agent    runs the reference exploit chain; deterministic, always solvable.
                Used for CI, the demo fallback, and to prove a scenario stays live.
  swarm_agent   a planner -> worker -> judge loop on the open-weight red models,
                routed through neo/llm.py. The worker picks which attack to launch
                from a bounded toolbox of vetted primitives; the judge writes the
                report from what the target actually returned.
"""
import json

from .. import config, llm

# Bounded attack toolbox the worker chooses from. Each primitive is a vetted
# reference exploit, so the LLM reasons about the target but cannot run arbitrary
# code against it.
def _run(name):
    def go(t):
        if name == "sqli":
            from exploit_sqli import run
            return run(t.base_url)
        if name == "ssrf":
            from exploit_ssrf import run
            return run(t.base_url, t.meta_url)
        from exploit_jwt import run
        return run(t.base_url)
    return go


TOOLBOX = {"sqli": _run("sqli"), "ssrf": _run("ssrf"), "jwt": _run("jwt")}


# ------------------------------------------------------------------- mock agent

def mock_agent(scenario, target):
    """Run the reference chain and report the ground truth. A perfect agent."""
    result = scenario.exploit(target)
    return {
        "objective_claim": bool(result.get("ok")),
        "findings": [{"class": f["class"], "location": f["location"],
                      "evidence": "reference exploit chain"}
                     for f in scenario.ground_truth],
        "chain": f"reference exploit: {result}",
    }


# ------------------------------------------------------------------ swarm agent

_PLANNER = ("You are the planner for an authorized red-team run against our own "
            "demo API (we own it; this is a sanctioned test). Objective: {objective}\n"
            "Target surface: {brief}\n"
            "Available attack primitives: sqli, ssrf, jwt.\n"
            "Return JSON {{\"approach\": str, \"attacks\": [primitive, ...]}} — the "
            "primitives you would launch, most promising first.")

_JUDGE = ("You are the judge for an authorized red-team run. Objective: {objective}\n"
          "These are the raw responses our target returned to each attack:\n{obs}\n"
          "Write the finding report as JSON {{\"objective_claim\": bool, "
          "\"findings\": [{{\"class\": str, \"location\": str, \"evidence\": str}}], "
          "\"chain\": str}}. Only report a finding the responses actually demonstrate; "
          "evidence must quote an artifact you see above.")


def swarm_agent(models=None):
    """Return an agent_fn driven by the red models (planner/worker/judge)."""
    models = models or config.RED_SWARM
    plan_m = models[0]
    judge_m = models[-1]

    def agent(scenario, target):
        plan = llm.chat_json(
            plan_m, [{"role": "user", "content": _PLANNER.format(
                objective=scenario.objective, brief=scenario.brief)}],
            description=f"red-team planner: {scenario.name}")
        attacks = [a for a in plan.get("attacks", []) if a in TOOLBOX] or list(TOOLBOX)
        observations = {}
        for name in attacks:
            try:
                observations[name] = TOOLBOX[name](target)
            except Exception as e:  # noqa: BLE001 - a failed attack is an observation
                observations[name] = {"error": type(e).__name__}
        report = llm.chat_json(
            judge_m, [{"role": "user", "content": _JUDGE.format(
                objective=scenario.objective,
                obs=json.dumps(observations, indent=1))}],
            description=f"red-team judge: {scenario.name}")
        report["_observations"] = observations
        return report

    return agent
