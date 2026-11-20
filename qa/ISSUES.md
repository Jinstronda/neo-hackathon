# NEO integration issues, release captain

Found by dogfooding the live preview, not the agents' reports. P0 blocks the golden path.
Each line names the owner who must fix it (ws21 = engine, ws18 = console/UI).

## P0

### P0-1 The live console shows a fixture, not a real engine run, ws21 + ws18
`/api/run` on the preview returns `source: "fixture"`. `ENGINE_URL` is unset on the neo-console
preview, and the engine (neo-hackathon) has no hosted `/api/run` and no recorded run bundled, so
the red-to-green flip on stage is fixture data, not a real server-side flag check. The pitch's
"nothing reaches your cloud without proof" needs a real run.
- Repro: `curl -H "x-vercel-protection-bypass: <secret>" <preview>/api/run | python3 -c "import json,sys;print(json.load(sys.stdin)['source'])"` -> `fixture`.
- Fix (ws21): produce one real run (`runs/<id>/run.json` + `events.jsonl`) from the loop against the demo target, and host the engine web (`neo-hackathon/web`, reads `NEO_RUN_DIR`) with a health endpoint, or deploy it as a second Vercel preview.
- Fix (ws18): set `ENGINE_URL` on the neo-console preview to that host, or, until the engine is hosted, bundle the recorded run as `neo-web/public/runs/demo-run.json` so the console serves `source: "recorded"` (honest) instead of the fixture.
- Verify: `qa/contract/check_contract.py <preview>/api/run --bypass <secret>` prints `source=engine` (or `recorded`) and all three checks PASS.

### P0-2 A judge cannot open the preview in a fresh browser, ws18
The neo-console project has Vercel SSO protection `all_except_custom_domains`, so every preview
URL redirects to a Vercel login. On stage, a fresh browser sees the login wall, not the console.
- Repro: `curl -so /dev/null -w "%{http_code}" <preview>/` -> `302` to vercel SSO.
- Fix (ws18): for the demo, either disable Deployment Protection on neo-console, or attach a custom domain (protection is `all_except_custom_domains`, so a custom domain is exempt), or hand the judges a share link. An automation bypass secret already exists and is what the e2e uses; do not rely on it for a human judge.

### P0-3 Deployed bundle predated the merge-phase fix, FIXED, verify on the demo deploy, ws18
The preview live at 12:12 streamed an empty `/api/stream?phase=merge`, so "Approved" rendered no
merge row. Current source maps `merge -> 'merge'` (lib/types.ts), the old bundle did not. I
redeployed current HEAD as preview `neo-console-6a7obii7r` where `phase=merge` streams the merge
event. ws18: make sure the URL shown on stage is built from the merge-phase code.

### P0-4 The "Approved" button does not merge, ws18
The suggestion button sends the bare word "Approved". gpt-6-luna reads it as conversation and
replies "Approved after re-running the exploit" without calling `approve_merge`, so no merge row
renders and the pitch's final beat (taps approve -> Merged) does not happen. The merge seam is
fine (phase=merge streams the merge event, verified); the model just does not call the tool.
- Repro: run the loop, click "Approved", the agent answers in text and never emits the merge.
- Fix (ws18): make "Approved" deterministic. Either the button sends an explicit "Approved, merge the PR" message, or it calls `play('merge')` directly alongside the message, or force `approve_merge` with toolChoice on an approve intent. The e2e now sends "Approved. Merge the PR now." to get past this; the stage button must be made as reliable.

## P1

### P1-1 Eve approve turn is slow (up to ~60s), ws18
The Eve agent reliably calls attack/fix/approve, but the "Approved" turn through the gateway can
take close to a minute. The pitch's 15s fallback rule will trigger if it stalls. Consider a
deterministic fallback: the suggestion button also calls `play()` so the screen advances even if
the agent is slow. The e2e waits 70s on this step.

### P1-2 /numbers is blank on a hard reload or deep link, ws18
`view().metrics` derives only from a streamed `metrics` event in `seen`, never from `run.metrics`.
Via the Numbers tab (client-side Link) after running the loop, it fills. A full reload or a deep
link to `/numbers` shows "No finished run yet" because `seen` is empty. Fix: fall back to
`run.metrics` in `lib/state.ts view()` when no metrics event is present.

### P1-3 Engine run outputs are committable and trip the secret scan, ws21
`gitleaks dir` on neo-hackathon finds a JWT in `runs/demo-run/events.jsonl`. It is the
weak-jwt-secret finding's own demo evidence (a forged token on a disposable twin), not a real
credential, so it is low severity. But `runs/` is only partly ignored (`runs/tmp/`,
`runs/.clone-*/`), so `runs/demo-run/` and `runs/prs/` would land in the public repo on a
`git add runs/`. Fix: gitignore all run outputs (`runs/*/`) or scrub the one run that gets
bundled. Git history is clean on both repos; `.env` is ignored.
