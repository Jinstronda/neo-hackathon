"""NEO scenario harness: isolated runs of the demo target with server-side
success checks. This is the substrate the red swarm drives. Apache-2.0.

The design follows the breachbench method (neo/skills/breachbench/SKILL.md):
randomized secrets per run, a planner/worker/judge agent loop, and a check that
reads only server-side state so an agent's claim is never the source of truth.

Submodules: target (boot the demo app), scenarios (the three definitions),
agent (mock + swarm planner/worker/judge), runner (run + score + journal)."""
