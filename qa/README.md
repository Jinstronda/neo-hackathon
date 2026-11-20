# qa, integration and release checks for the NEO demo

I own this directory. It proves the console and the engine agree, and that the stage demo holds
up on the live URL. Nothing here edits the engine or the UI; it tests them.

## What is here

- `schema/run.schema.json`, the run contract (run.json + events), from `neo/journal.py` and `docs/RUN_SCHEMA.md`.
- `contract/check_contract.py`, validates a run (file or live `/api/run`) against the schema, checks the server-side retest gate (exploit works pre-patch, dead post-patch), and checks that every field the console reads exists in what the engine sends. Stdlib only.
- `e2e/golden_path.spec.ts`, the stage script as a Playwright test: open the console, tell NEO to attack, follow the loop to a merged PR and the numbers. Every assertion reads the expected value from `/api/run`, never from text the UI hardcodes.
- `e2e/fault_injection.spec.ts`, engine down, Eve down, double click, slow stream. Each must degrade honestly.
- `deploy/README.md`, how to make the live path real (host the engine, set `ENGINE_URL`, open the preview to judges).
- `raw/`, live responses saved from the preview, for the record.
- `runs/`, e2e video, trace, HAR and per-step screenshots, one folder per round.
- `ISSUES.md`, the P0/P1 bugs found, with owner and exact fix.

## Run

```bash
export NEO_BYPASS=<vercel automation bypass secret>   # keep out of the repo
python3 contract/check_contract.py <preview>/api/run --bypass "$NEO_BYPASS"
e2e/run.sh <preview-url> 3
cd e2e && BASE_URL=<preview-url> NEO_BYPASS=$NEO_BYPASS npx playwright test fault_injection.spec.ts
```

## State on 2026-11-20

The console chat, the Eve agent and its tool calls are live. The run data (board, timeline,
numbers) and the red-to-green flip are the fixture: `ENGINE_URL` is unset and the engine has no
hosted run yet. See `ISSUES.md` P0-1. The contract passes on the served fixture, which means the
seam is correct; it is waiting on a real engine run to carry real proof.
