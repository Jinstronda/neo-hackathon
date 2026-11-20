# NEO skills

The methodology NEO runs by. Each `SKILL.md` is a prescriptive doc the engine's
own prompts cite: the planner, judge and reporting steps load the matching skill
so the rules below govern a real run, not just documentation. The discipline is
the point. A CVE is not a finding, a model's claim is not proof, and a severity
grade is earned against a hostile reviewer, never assumed.

## The skills

**breachbench**, the full-chain regression harness. Isolated, randomized
scenarios (SQLi->traversal, SSRF->metadata->cred-reuse, JWT forgery) with an
independent server-side check that decides PASS/FAIL, never the agent's own
report. `neo/harness/` is this engine and `neo/red.py` drives it; the regression
protocol here is how a model or skill change is proven not to regress before it
ships.

**cve-intake**, the fresh-CVE radar and the adoption gate. Pull recent
disclosures that already have a public exploit, filter them against the stack
actually fingerprinted on the target, prove the PoC locally (vulnerable build
fires, patched build does not), and only then weaponize. `neo/radar.py` is the
radar: it SBOMs the target and matches it against KEV, EPSS and OSV, ranking the
worklist it hands to the swarm. The adoption gates keep attacker code of unknown
quality out of a client run.

**nday-pwn**, version -> fresh CVE -> public exploit -> pwn. Deep version
fingerprinting (headers, version files, favicon hashing, passive sources), CPE
construction, KEV/EPSS/CVSS prioritization, PoC location and adaptation, and
verified exploitation. It consumes `cve-intake`'s worklist, runs inside the
`breachbench` kill chain, and every finding goes through `adversary-review`.

**supply-chain-pwn**, compromise the target through what they install: a
typosquatted package, a poisoned MCP server or AI skill, a compromised upstream,
a malicious LLM router. Maps the dependency surface, builds the lure, delivers
passively and pivots from the install. Runs inside the `breachbench` kill chain;
findings go through `adversary-review`.

**attack-graph**, one connected, validated target state the whole swarm shares.
Typed records (assets, identities, privileges, data, footholds), evidence-gated
`proven` edges, a provenance taxonomy that doubles as the prompt-injection
firewall (target-controlled text can never prove a boundary crossing), anchors
that stop parallel workers colliding, and a coverage ledger whose absence of a
record is a gap, never a clean result. Red workers write their confirmed
discoveries into it so the next wave plans against fresh state.

**adversary-review**, the severity calibration gate, run before any finding
reaches a report. Five mechanical gates (quote-in-artifact, proof-of-exploitation
floor, provenance, denominator, retest) then seven written questions, graded
against CERT/CC + CVSS 3.1 + the MSRC bug bar. It splits demonstrated from
potential impact and downgrades anything that fails. This is the gate `neo/red.py`
and every offensive skill pass every finding through; it exists to kill the #1
failure mode, calling something a big vulnerability when it isn't.

**disclosure-report**, the client-facing report, which is both the value
delivery and the legal shield. CVSS/CWE, monochrome figures, documented financial
math only, evidence-matched claims, and a long list of hard rules that keep zero
legal self-exposure (no log-refutable denials, no absolute denials we can't
survive, no extortion optics, never admit writes). Runs after a mission once
cleanup is complete and `adversary-review` has graded every finding.

## How the engine uses them

- `neo/harness/agent.py`, the planner and judge prompts cite `breachbench`
  (server-side evidence decides, not the agent) and `adversary-review` (evidence
  must quote an artifact; report only what the responses demonstrate).
- `neo/radar.py`, the module docstring cites `cve-intake`: the radar is a
  worklist, proof comes later when the exploit fires on the twin and dies on the
  patch.
- `neo/red.py`, cites `breachbench` (a finding counts only when the server-side
  check confirms it or a second model reproduces the class) and `adversary-review`
  (grade demonstrated impact, never potential).
