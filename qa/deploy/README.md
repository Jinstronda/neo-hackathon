# Wiring the live path

The console (`neo-web`, Vercel project `neo-console`, team `team_pMnXG6LWTwQVyiogbw7CeoZ3`)
reads a run from `ENGINE_URL/api/run` and talks to the Eve agent at `EVE_URL`. Today the preview
has `EVE_URL` and `NEO_EVE_SECRET` set (chat is live) but no `ENGINE_URL`, so the run data is the
bundled fixture. These are the steps to make the run real, in the order that unblocks the demo.

## 1. Host the engine API

The engine ships a thin data API in `neo-hackathon/web` that serves `/api/run`, `/api/stream` and
`/api/chat` from `NEO_RUN_DIR`. Point it at a real run and run it where Vercel can reach it.

```bash
# on the organizer box (ubuntu@173.234.68.156), from the repo root
NEO_RUN_DIR=../runs/<real-run-id> npm --prefix web run build
NEO_RUN_DIR=../runs/<real-run-id> PORT=8080 npm --prefix web run start   # behind a health check
```

A run is real when `runs/<id>/run.json` and `events.jsonl` exist and pass the contract:

```bash
python3 qa/contract/check_contract.py runs/<id>/run.json   # source=engine, all PASS
```

## 2. Point the console at it

```bash
cd neo-web
vercel env add ENGINE_URL preview --scope team_pMnXG6LWTwQVyiogbw7CeoZ3   # http://173.234.68.156:8080
vercel deploy --yes --scope team_pMnXG6LWTwQVyiogbw7CeoZ3
```

Verify the live console now serves engine data, not the fixture:

```bash
python3 qa/contract/check_contract.py <new-preview>/api/run --bypass "$NEO_BYPASS"   # source=engine
```

## 3. If the engine cannot be hosted in time

Bundle the real recorded run so the console serves `source: "recorded"` (honest), not the fixture:

```bash
cp runs/<id>/run.json  neo-web/public/runs/demo-run.json   # the console reads demo-run.json first
# shape: { "run": {...}, "events": [...] }  (wrap run.json + parsed events.jsonl)
```

The console's `lib/engine.ts` already prefers `public/runs/demo-run.json` (recorded) over the
fixture. Do not relabel the fixture as recorded; that defeats the point.

## 4. Open it to judges

The project has Vercel SSO protection `all_except_custom_domains`. A fresh browser hits a login
wall. Before stage: disable Deployment Protection on `neo-console`, or attach a custom domain
(exempt under `all_except_custom_domains`), or hand out a share link. The automation bypass secret
is for the e2e only, not for a human judge.

## Running the checks

```bash
# contract (deterministic, no browser)
python3 qa/contract/check_contract.py <url>/api/run --bypass "$NEO_BYPASS"

# golden path, 3 rounds, on the live preview
export NEO_BYPASS=<automation-bypass-secret>   # never commit this
qa/e2e/run.sh <preview-url> 3

# fault injection
cd qa/e2e && BASE_URL=<preview-url> NEO_BYPASS=$NEO_BYPASS npx playwright test fault_injection.spec.ts
```

The bypass secret lives in the Vercel project's protection-bypass settings. Keep it out of the
repo, logs, screenshots and messages.
