# Security

NEO attacks software. That makes how it is used, and how it is built, part of the product.

## Use it only on systems you may test

Point NEO only at code and systems you own, or that you have written permission to test. The red
swarm attacks a disposable twin: a throwaway copy of the target with fresh random secrets, bound to
`127.0.0.1` and torn down after the run. It never attacks the system the twin was copied from.

`demo-target/` is vulnerable on purpose: a SQL injection, an SSRF chain, a forgeable JWT and an
outdated PyYAML pin. Run it only on your own machine or inside a twin. Do not deploy it anywhere a
network can reach.

During the hackathon the organizer provided a server. I ran only NEO's own containers on it, and the
only thing NEO attacked there was its own twins.

## Report a vulnerability in NEO

Use GitHub's private vulnerability reporting on this repository: the Security tab, then "Report a
vulnerability". If that option is not shown, open an issue that says only that you have a security
report and asks for a private contact. Do not put details in a public issue.

In scope: the engine (`neo/`), the gate and twins (`infra/`), the flag checks (`checks/`), the CI
workflows, and anything that could make NEO attack something other than its twin, mark a live
exploit as dead, approve a diff nobody reviewed, or leak a secret. Out of scope: the planted bugs
in `demo-target/`, which exist so NEO has something to find.

## How NEO limits itself

- Attacks run only on twins. Each red model gets its own copy, with its own secrets and event log.
- Models pick from a fixed toolbox of vetted exploit primitives (`neo/harness/agent.py`). A model
  can reason about the target; it cannot send the target arbitrary code.
- Only the target decides. Server-side flag checks in `checks/` read the twin's event log. A model's
  report, or an exploit's exit code, never marks an attack as working or a fix as done.
- Reviewers treat the diff, the finding and repo text as untrusted data inside `<untrusted>` tags,
  and every claim must quote a real line of the diff.
- A human merges. NEO opens the PR and computes readiness; `neo/factory` refuses to record a release
  without a human merge signal.
- No secret lives in the repo. The gateway key and twin credentials come from `.env`, which git
  ignores. Every model call goes through `neo/llm.py`, which reads the key from the environment.
- CI runs with `contents: read` and replays exploits with `set -o pipefail`, so a live exploit fails
  the job.
- The terminal view strips control bytes from every event before printing it, because exploit
  output and model text are untrusted.
