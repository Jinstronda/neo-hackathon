---
name: supply-chain-pwn
description: Compromise the target through their dependencies, publish or poison a package, MCP server, AI skill, or vendor the target consumes, then pivot from the install into their environment. Use to hack a target via supply chain, typosquat packages, malicious skills/MCP, or third-party/vendor compromise (M-Trends 2026 lists third-party compromise as a top cloud vector). Autonomous, no contact with target humans; run inside the breachbench kill chain.
---

# supply-chain-pwn: hack the target through what they install

You don't touch the target's perimeter, you become something they trust and
pull. Proven 2026 operations:

- **FakeGit / AgentBaiting**: ~7,600 malicious GitHub repos, 14M+ downloads, 800+
  posing as AI Skills/MCP servers; listings spread across registries. AI agents
  discover the lure themselves during tasks and hand the install instructions to
  the user.
- **ClawHavoc**: 341 of 2,857 skills on one registry malicious, instructions
  hidden in SKILL.md files, delivering a stealer via the agent as trusted installer.
- **Trivy -> LiteLLM**: attackers rewrote release tags, stole publishing creds,
  pushed malicious PyPI versions; one AI vendor lost ~4 TB of data.
- **Malicious LLM API routers** (router-in-the-middle): routers see every
  tool-call JSON in plaintext, rewrite install URLs/dependency names, exfil
  every credential in transit (99 creds across 440 sessions in one study, 401 in
  auto-approve YOLO mode).
- **M-Trends 2026**: compromising third-party SaaS vendors for hard-coded
  keys/PATs, then pivoting into downstream customers is a top cloud compromise path.

## Stage 1, map the target's dependency surface

From recon: the target's public code, `package.json`, `requirements.txt`,
cargo/manifests, agent directories, MCP configs, skills directories, browser
extensions. Job posts/leaks revealing internal stack (npm/PyPI/GitHub Actions,
observability, auth vendors). LLM infrastructure: API routers/gateways they use.

## Stage 2, choose the vector (ranked by yield)

1. **Fake AI capability (skill/MCP)**, publish to GitHub + the public
   registries; let discovery do the distribution. The target's own agent can find
   the lure, read your README as documentation, and recommend the install.
2. **Typosquat/homoglyph package** on npm/PyPI/cargo, visually similar name
   substituted into `pip install`/`npm install` lines; LLM approval UIs mistake
   near-homographs for the correct name.
3. **Compromised upstream**, steal maintainer creds, rewrite release tags
   (Trivy pattern) to capture downstream publishing creds.
4. **Poisoned tool description** (MCP tool poisoning), instructions in metadata
   the UI never shows.
5. **Malicious LLM router**, if the target routes agent traffic through a
   third-party relay: payload injection + secret exfiltration at the
   JSON/tool-call layer, outside the model's reasoning loop (composes with,
   doesn't replace, prompt injection).

## Stage 3, build the lure (FakeGit pattern)

- Copy or fabricate a project under a lookalike identity (profile names one char
  off from established devs).
- Credible README: borrow names/workflows of familiar enterprise tools;
  "Download Latest Release" -> your artifact.
- Agent-era simplification: a SKILL.md/README whose instructions tell the
  target's own agent to run the implant, the agent is both installer and alibi.
- Rule of thumb for realism: a legitimate skill/MCP is source + manifest;
  anything installing via a downloaded executable is malware on sight, mirror
  the ecosystem's real look.

## Stage 4, deliver, then wait

Prefer passive: registry/marketplace listings distribute for you; verify the
target pulls (downloads, install callbacks, canary creds used from target IPs).
The target's agent may discover the lure mid-task and recommend it, AgentBaiting
measured multiple major agents surfacing campaign repos unprompted. Active push
only if the operator approves target contact.

Payload goals ranked: credential harvest (SSH/AWS/K8s/GitHub tokens, harvest
inside trusted, signed processes EDR ignores), durable persistence, staged
exfiltration, pivot to the vendor's other customers.

## Stage 5, pivot & verify

Treat stolen keys (cloud, git, registry, API) as a foothold -> continue in the
breachbench kill chain (staged exfiltration, persistence, evidence). Refutation
gate: confirm implant execution, webhook callback with a canary value, creds
used from target infrastructure.

## Report

State: vector chosen, lure identity, distribution evidence
(listing/downloads/callbacks), credentials/data obtained with classification,
downstream pivot performed. Defensive note for us: this same class targets our
own skill directory, audit anything we import before loading it.

**Adversary review (mandatory, always runs):** before writing this section, run
`adversary-review` on every finding and severity claim, a lure with downloads
but no target pull is a lead; a harvested key nobody used from target infra is
potential, not demonstrated. No severity grade leaves the mission without its verdict.

Sources: island.io (AgentBaiting) · trendaisecurity.com (ClawHavoc, Trivy/LiteLLM) ·
arXiv 2604.08407 (malicious LLM routers) · M-Trends 2026 (third-party compromise).
