# Run artifact schema

The engine writes one run per loop under `runs/<id>/`:

- `events.jsonl`, one JSON event per line, in order (see `neo/journal.py` for the vocabulary).
- `run.json`, the summary the web UI loads: `{ id, title, date, where, agents, steps, metrics, radar, findings, approval, pr, review, retest, merge, verification }`. A run that stopped before blue keeps `pr`, `review`, `retest` and `verification` as `null`, and `merge.blockers` says why it stopped.

With screenshots on, `neo/shots.py` also writes one PNG per step to the repo's `screenshots/`
(optional; the UI falls back to drawing from events).

`run.json` shape the web app reads:

```json
{
  "id": "demo-run",
  "title": "NEO closed-loop run",
  "date": "2026-11-20",
  "where": "EU",
  "agents": [
    {"id": "neo-1", "role": "red", "label": "model-1", "status": "done"},
    {"id": "neo-2", "role": "red", "label": "model-2", "status": "done"},
    {"id": "blue", "role": "blue", "label": "fixer", "status": "done"},
    {"id": "rev-sec", "role": "reviewer", "label": "security", "status": "approve"},
    {"id": "rev-cor", "role": "reviewer", "label": "correctness", "status": "approve"}
  ],
  "steps": [
    {"key": "radar", "title": "Radar match", "live": false, "events": ["radar_match"]},
    {"key": "red", "title": "NEO proves the exploit", "live": true, "events": ["red_start","red_finding","flag_check"]},
    {"key": "blue", "title": "Blue opens the patch PR", "live": true, "events": ["fix_approval","fix_attempt","blue_patch"]},
    {"key": "review", "title": "Two reviewers check the PR", "live": true, "events": ["review"]},
    {"key": "retest", "title": "Twin rebuilt, exploit replayed", "live": true, "events": ["twin_deploy","retest","tests"]},
    {"key": "merge", "title": "Human merges", "live": false, "events": ["merge_ready","merge"]}
  ],
  "metrics": {
    "minutes_exploit_to_fix": 0,
    "cost_usd": 0,
    "where": "EU",
    "tested_surface": 0,
    "untested_surface": 0,
    "regression_tests": 0
  }
}
```

Every `flag_check` with `phase:"pre-patch"` must have `objective_complete:true` (exploit works),
every `phase:"post-patch"` must have `objective_complete:false` (exploit dead). That contrast is
the retest gate, decided server-side, never by an agent's claim.

## Events for the human gate, the fix loop and 24/7 mode

The full vocabulary is the comment at the bottom of `neo/journal.py`. These events cover the human
fix gate, the blue loop-back and `neo watch`:

| Event | Fields | When |
|---|---|---|
| `fix_approval` | `approved: bool`, `by: "human" \| "auto"` | After red proves at least one exploit and before blue runs. `by:"auto"` when no human was asked. |
| `fix_attempt` | `attempt: int`, `of: int`, `source: "model" \| "canonical"`, `ok: bool`, `exploits_dead: {scenario: bool}`, `legit_login_ok: bool`, `error?: str` | Once per blue try. Each candidate patch is replayed on a fresh copy; `ok` is true only when every exploit is dead and a normal login still works. A failed model try loops back to the fixer with what still landed; the canonical try is the floor. `error` says why a patch could not be tested at all. |
| `watch_tick` | `cycle: int`, `new_matches: int`, `kev_source: str`, `next_in_s: int` | Once per `neo watch` cycle, after the radar rescans the feeds. |
| `watch_trigger` | `cve: str`, `package: str`, `version: str`, `run_id: str` | When a cycle finds a new match and starts a loop run for it. |
| `watch_error` | `error: str`, plus `cycle: int` or `run_id: str, cve: str` | When a feed scan or a triggered run fails. The match stays unseen, so the next cycle retries it. |

`neo watch` writes these to `runs/watch/events.jsonl` and keeps the matches it has seen in
`runs/watch/state.json`. Each triggered run writes its own `runs/<run_id>/`.

When a human declines the fix, the run stops before blue: `events.jsonl` ends with
`fix_approval {approved:false}` and `run.json` carries `merge.awaiting = "fix approval"`.
