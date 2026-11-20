# Run artifact schema

The engine writes one run per loop under `runs/<id>/`:

- `events.jsonl`, one JSON event per line, in order (see `neo/journal.py` for the vocabulary).
- `run.json`, the summary the web UI loads: `{ id, title, date, live_steps, recorded_steps, agents, steps, metrics }`.
- `screenshots/`, one PNG per step (optional; the UI falls back to drawing from events).

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
    {"key": "blue", "title": "Blue opens the patch PR", "live": true, "events": ["blue_patch"]},
    {"key": "review", "title": "Two reviewers check the PR", "live": true, "events": ["review"]},
    {"key": "retest", "title": "Twin rebuilt, exploit replayed", "live": true, "events": ["twin_deploy","retest","tests"]},
    {"key": "merge", "title": "Human merges", "live": false, "events": ["merge"]}
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
