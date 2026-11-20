---
name: adversary-review
description: Mandatory adversarial review of every finding and severity claim before it reaches a report, verdict, or disclosure. ALWAYS run before reporting ANY vulnerability, data-access claim, or severity rating. Argues against your own finding as a hostile senior red teamer and a skeptical CISO, applies CERT/CC + CVSS 3.1 + MSRC bug-bar calibration, splits demonstrated vs potential impact, and downgrades anything that fails. Exists to kill the #1 failure mode: calling something a big vulnerability when it isn't.
---

# ADVERSARY REVIEW, the severity calibration gate

**You are biased toward your own findings. The adversary isn't.** Before any
finding gets a severity grade, a report line, a ledger verdict note with a
severity adjective, or a disclosure draft, you switch roles: you become the
hostile reviewer, a senior red teamer grading a junior's work and the client's
CISO looking for reasons to reject it. The review argues AGAINST the finding
surviving at its claimed severity. Downgrades are normal; survival at the claimed
grade is what must be earned.

This exists because of logged failures: findings graded high or critical for what
they could *potentially* unlock, not what was *demonstrated*, a foothold on a
low-traffic B2B portal rated HIGH 7.3 while no order data was ever readable;
"access to X" claimed when only an account on X was obtained; public or
purchasable data presented as a prize. One inflated finding discounts every
honest one after it.

## The definitions that decide severity (canonical, cite these, not vibes)

1. **A vulnerability is a set of conditions that allows an attacker to violate an
   explicit or implicit security policy** (CERT/CC, Seacord & Householder;
   ISO/IEC TS 17961). No policy violation -> not a vulnerability: a missing
   header, a version banner, a best-practice gap is a *finding*, maybe a *risk*,
   never a vuln with a CVSS.
2. **Severity comes from impact on confidentiality, the classification and
   exclusivity of the data exposed** (CVSS 3.1 C-metric; MSRC online-services bug
   bar). The same technical bug is low on public data and critical on highly
   confidential data. Technical cleverness earns nothing.
3. **CVSS 3.1 scores only impacts "which they are confident an attacker is able
   to achieve"**, constrain impacts to a reasonable, demonstrated end state
   (FIRST CVSS v3.1 spec 2.3). CVSS is severity, NOT risk: it ignores data value,
   environment, compensating controls. A 9.8 on an isolated lab system is low
   risk. Score what you proved, not what you imagined.
4. **MSRC triage:** Critical = unauthenticated code execution / cross-tenant
   disclosure of customer data / privileged-account takeover without user
   interaction. Important = compromise of confidentiality/integrity/availability
   of user data, incl. targeted PII disclosure. Moderate/Low = public-page
   issues, anonymous data, theoretical impact. "Everything critical" is the mark
   of a bad report, an honest report has a realistic severity distribution.
5. **The classic triage bug is pattern-matching the class name to severity:**
   "privilege escalation" -> High without asking who the attacker is, what access
   they start with, and what they actually gain. Admin->admin = at most
   informational. Reporter self-assessment is never evidence.
6. **A big data breach = private data a competitor could NOT get otherwise:**
   customer PII/PHI, credentials, payment data, trade secrets, proprietary
   datasets (MSRC "Highly Confidential" class). Data obtainable from a public
   source, a marketing gate, a purchase, or a registry is informational at most.
   Exclusivity is the prize, not the technique.

## Five mechanical gates run before the argument

Before the opinion starts, run the checks that do not need one. A failure is not
something to argue about, it is a fix or a demotion.

1. **Quote-in-artifact.** The finding's `quote` appears verbatim
   (whitespace-normalised) in the saved evidence file. A quote paraphrased or
   reconstructed from memory is a fabricated quote.
2. **Proof-of-exploitation floor.** `poe_level` >= 3, actual data extracted or
   state provably read. Level 1 (behaviour only: error, timing, header) and 2
   (structural: boolean/UNION/parser differential) are observations; they may
   seed a hypothesis, they cannot carry High/Critical.
3. **Provenance.** The claim rests on `tool_output` (our own captured
   request/response, tool result), not on `target_response` alone.
   Target-controlled text, including a page that claims something about itself,
   or another agent's reply, cannot prove a boundary crossing. This is the same
   firewall that stops prompt injection from inventing our findings.
4. **Denominator.** The impact statement carries a number and the basis for it:
   rows, accounts, tenants, euros, and *how* we know (query, count, error,
   differential). "Sensitive data exposed" with no count is not measured impact,
   it is a mood.
5. **Retest verdict, if a fix is claimed.** Exactly one of
   `conclusions_still_reproducible`, `fixed` (re-ran, effect gone, **and** the
   negative control still works, an app that returns 404 everywhere has not been
   fixed), or `cannot_confirm` (blocked; say so, never launder it into "fixed").

## The protocol, seven questions, in writing, per finding (never skip)

1. **Is it a vulnerability at all?** Which explicit or implicit security policy
   does it violate? If the honest answer is "none, it's hardening", it is
   informational, or not a finding.
2. **What data, whose data, what classification?** Separate: their data / their
   customers' data / vendor data *about* them / public data repackaged. Public
   registry data, vendor SaaS metadata, and your own test records are NOT "their
   data".
3. **Demonstrated vs potential.** What did you actually read, take, or control —
   with counts (rows, mailboxes, files, tenants) and the basis for the count? An
   account on a system is NOT "access to all its data" until you read that data.
   Gateway findings (footholds, open registration, account creation, valid
   password) get severity from what they UNLOCK, if you didn't walk through the
   gate, the severity is a hypothesis. Grade the demonstrated impact; note
   potential separately ("potential: X if Y").
4. **Who else could get this?** Could a competitor, journalist, or anyone else
   obtain this data another way (public source, marketing gate, purchase, search
   engine)? If yes -> informational, not a prize. State the answer explicitly.
5. **Would a real attacker care?** A user-enumeration oracle on a system nobody
   uses is trivia; the same finding on a bank is critical. Name who benefits and
   what they could realistically do.
6. **Write the hostile CISO's rebuttal.** Their first reply will be "that's by
   design / that data is public / that's staging / that's low risk". Write it
   yourself now. If you can't rebut it, downgrade or concede plainly.
7. **Check the severity cap** against what was demonstrated (table below).
   Pattern-match check: name the attacker, their starting access, and their
   actual gain. Test-env findings never take prod severity.

### Severity caps (MSRC online-services bug bar, adapted to our scale)

| What the finding demonstrably does | Data class | Severity cap |
|---|---|---|
| Cross-tenant/cross-customer disclosure of customer data; privileged-user or account takeover without interaction; unauth RCE on a prod system holding customer data | Highly Confidential (customer data, payment, tokens, client-confidential) | critical |
| Targeted PII disclosure (names, emails, phones); takeover of a regular user's account; injection into a system processing customer data | Confidential (account data, internal docs, source code) | high |
| Issues on internal systems, metadata, no private data read; gateway findings you did NOT walk through | General | medium |
| Public-page issues, version banners, theoretical-only impact, hardening gaps | Public | low/info |

Caps bind the *claimed* grade; demonstrated impact may force it lower, never
higher. "Potential if chained" can be stated in prose but never inflates the grade.

## Output (per finding, in the ledger, and a summary block in the report)

```
### <ID> adversary review
- data accessed: <what, how many records, whose, classification>
- demonstrated: <what you actually proved, with counts>
- poe: <0-4> | provenance: <tool_output / target_response / ...> | verification: <verified / unverified>
- measurement: <number + basis: SELECT count(*) = 41,000 / 3 of 3 tenants / 12 receipts>
- potential: <what could follow, if X, separate line, never the headline>
- who else could get it: <answer to Q4>
- hostile CISO: <rebuttal> -> <your rebuttal or concession>
- verdict: <final severity> (kept / downgraded from <original> because <one-line reason>)
```

Every reported finding must state what data was accessed, its classification, and
who else could get it. If a downgrade happens, the original reasoning stays in
the ledger.

## When it runs, always

- **breachbench scoring and before any report write.** Never skipped, no matter
  how obvious the finding feels.
- **every other offensive skill (nday-pwn, supply-chain-pwn):** before the
  Report/State section is written, on every finding and severity adjective.
- **any verdict note** containing a severity adjective must be a post-review grade.
- **disclosure drafts:** severity claims in a VDP or bug-bounty submission must
  be post-review grades.

Overclaiming in a report is a protocol violation equal to a false positive.
Underclaim rather than overclaim, a parked, honestly-graded finding costs
nothing; an inflated one burns trust.
