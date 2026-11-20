# NEO

Nothing reaches your cloud without proof.

I built this at Hackathon Portugal 2026, hosted by Leaseweb and Velv at DeHouse in Lisbon, for the
"AI for Cloud Infrastructure" challenge, direction 3: track new exploits and help find, patch and
mitigate them.

Attackers already point AI at every target on the internet. A security team cannot read every
diff and run every scanner by hand fast enough to keep up. NEO is the other side of that: an AI
team that attacks your own system first, on a disposable copy, proves the hole is real, writes the
fix, and proves the fix closes the hole before a human merges anything.

## The loop

1. **Radar.** NEO builds an SBOM of the target, matches it against the CISA KEV feed, EPSS and
   OSV, and ranks what to look at first: in KEV, then high EPSS, then reachable from the app.
2. **Red.** A small swarm of open-weight models, each in its own disposable twin, attacks the
   target. A finding only counts when a server-side check on the twin confirms it, or a second
   model reproduces it. The agents never get to grade their own work.
3. **Blue.** A fixer model reads the finding and the code and opens a real pull request: the
   patch, the exploit request and response, and the server-side proof that the hole was open
   before the patch.
4. **Review.** Two reviewers from two different vendors read the diff. Each one re-derives its own
   claim from the diff before it posts, not just repeats the first draft. Both have to approve.
   Disagreement goes to a human with both opinions side by side, not to a vote.
5. **Retest.** A fresh twin is built from the patched code, the exact same exploit runs again, and
   the gate reads the result from the twin's own server-side log. The pull request can merge only
   when the exploit is dead, the tests are green, and both reviewers approved that exact diff. A
   human presses merge.
6. **Memory.** Every exploit NEO proves becomes a permanent regression test and an attack replay
   that runs in CI forever, so a closed bug cannot come back silently.

The whole loop ran for real while I built it: a KEV entry landed, the radar matched it, the red
swarm proved a SQL injection, an SSRF chain and a forged JWT on a disposable twin, the fixer opened
[pull request #1](https://github.com/Jinstronda/neo-hackathon/pull/1), one reviewer approved and
the other asked for changes on a technicality, and a rebuilt twin showed all three exploits dead
with ten tests passing. The run, the PR, and the reviews are in this repo, not staged for a demo.

## What it is built from

Everything here is new code written for this hackathon, Apache-2.0, mostly Python with a
TypeScript console. The design borrows from work I already own: a breachbench-style harness with
randomized, server-verified scenarios, and a KEV/EPSS/OSV radar, both rebuilt clean for this repo
rather than copied, since the originals carry a different license. The scanning tools underneath
(Trivy, OSV-Scanner, Syft) are the usual open-source choices, all Apache-2.0 or MIT. The models
behind the red and blue agents are open-weight, running on our own EU servers, and reached only
through a shared LLM gateway, so no raw API key sits in this repo.

## Try it

The live console: [neo-console.vercel.app](https://neo-console.vercel.app). It replays the real
run above by default; signing in with the team login lets it talk to a live engine run instead.

To run the loop yourself:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r demo-target/requirements.txt pytest

cp .env.example .env   # fill in HOMODEUS_API_KEY and, if you have one, a twin SSH host

python3 -m pytest tests/              # the regression suite: every fixed bug stays fixed
python3 -m neo.harness.runner run --all --agent mock   # the harness, no LLM calls
python3 -m neo                        # the real loop: radar, red, blue, review, retest
```

`neo/config.py` holds the model ids for each role. `neo/llm.py` is the one place every model call
goes through; nothing in this repo calls a provider SDK directly.

## Structure

- `demo-target/`, the vulnerable demo app the whole loop attacks: a SQL injection auth bypass, an
  SSRF chain to a fake metadata service, a forged-JWT admin bypass, and one outdated dependency
  with a real CVE in the CISA KEV catalog. `FIXES.md` documents the intended fix for each, applied
  live by the blue agent, never checked in ahead of time.
- `checks/`, the server-side flag checks. They read only the target's own event log. An agent's
  claim is never the source of truth.
- `neo/harness/`, the scenario runner: boots an isolated copy of the target with fresh random
  secrets, runs the attack, scores it against ground truth.
- `neo/radar.py`, the KEV/EPSS/OSV matcher.
- `neo/red.py`, `neo/blue.py`, `neo/gate.py`, `neo/orchestrator.py`, the loop itself.
- `neo/factory/`, `neo/reviewers.py`, opens the pull request, runs the two-vendor review, and
  refuses to call anything "ready to merge" until the retest is green and both reviewers approved
  that exact diff.
- `infra/`, builds a disposable twin, locally in Docker or on a remote box over SSH.
- `tests/`, the regression and attack-replay suite that grows by one case every time NEO closes a
  bug.
- `console/`, the Next.js app at neo-console.vercel.app: the agent board, the incident timeline,
  the radar, the numbers, and a chat that talks to the loop.
- `runs/demo-run/`, the real run from this session: every event, the patch, the reviews, the
  before-and-after proof.

## License

Apache-2.0. See `LICENSE`.
