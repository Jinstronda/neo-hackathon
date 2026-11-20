---
name: disclosure-report
description: Produces the professional vulnerability disclosure report for an assessed target (EU focus, also PT-BR), with CVSS/CWE, monochrome figures and financial scenarios. Calibrates wording against EU cybersecurity law and disclosure best practice. Core invariant: show the vulnerability and drive the engagement with ZERO legal self-exposure. Use whenever a client-facing report, executive document, or disclosure package is needed after a breach mission.
---

# Disclosure Report

## When to use
After a breach mission, when a client-facing report is ordered. The report is
both the value delivery and the legal shield. Read our internal legal position
and the wording-calibration playbook BEFORE writing a single sentence.

## Pipeline

1. Copy the canonical template (build + figures) into the mission's report dir.
2. Write the document (structure below). PT-PT for Portuguese targets, PT-BR for
   Brazilian, EN otherwise.
3. Adapt the figures to the finding's real numbers (composition of exposed base,
   ceilings/precedents, financial scenarios). Monochrome only: INK #161B22,
   SLATE #1F2937, GRAY #8A9098, hairlines #D7DADE.
4. Adapt the footer ("Confidencial · NEO para <Target> · <Month Year>").
5. Build DOCX + PDF.
6. Run the verification gate (below). Only then show the operator.

## Document structure

1. Context and objective (one exposure, one central recommendation, no laws)
2. Scope, window and methodology (autonomous scan, point reads, the system's own
   aggregation functions, adversarial review)
3. Overview (findings table: severity, CVSS 3.1 base, CWE, system)
4. Finding(s) (system, vector, what is readable, composition figure, attack
   vectors, reproduction, recommendations)
5. Potential financial impact (hypothetical "if exploited by criminals":
   regulator fine as ONE cost row, response, civil, commercial; scenario figure)
6. Conduct and good faith (see rules below)
7. Coordination and next steps (confidentiality, ratification offer, free closure
   validation, pilot offer)

Severity: CVSS 3.1 base score ALWAYS published side by side with contextual
classification (base measures one record; classification measures the whole
base). CWE map to OWASP Top 10.

## Hard rules (violating any of these can burn us)

0. **No log-refutable denials.** NEVER write absolute "no records transferred",
   "read-only access", "no internal credentials", "no system altered". If logs
   can refute it, do not write it. Safe patterns: "read access limited to what
   the finding required to validate"; "as of this document, no system remains
   altered"; counts "derive from the assessed system's own count functions"
   WITHOUT the no-transfer clause. The disclosed validation must be the
   vulnerability condition, not our full activity.
1. **No laws in the client doc.** No regulation articles, no notification-duty
   hours, no authority notification instructions, no statute numbers. The law
   lives in our internal analysis and the call. Exception: one generic cost label
   row (e.g. "Regulatory fine (GDPR)") inside a hypothetical "if exploited by
   criminals" table is allowed.
2. **No absolute denials we can't survive.** NEVER write "no data extracted", "no
   session started", "no account created", "we did not download data". If they
   check logs later, a false written statement is worse than silence. Write only
   positive true conduct: "point-in-time, read-only access", "no system altered,
   damaged or made unavailable" (true after cleanup).
3. **Counts via system-aggregation framing:** "the counts derive from the
   assessed system's own count and aggregation functions, without record transfer".
4. **No extortion optics:** no payment demands, no countdown, no "we have your
   data", no threats. Value framing: "closure validation at no cost", "if there
   is interest".
5. **Scope discipline:** only the vulnerabilities the operator authorized. No
   evidence of deeper access, no other findings, no account names we created, no
   methodology that points to our infrastructure.
6. **Ratification offer in next steps:** "a confidentiality and ratification term
   formalizing the authorization of this disclosure".
7. **One recipient first:** recommend sending to ONE decision-maker who already
   knows us, not a blast. Wide blasts read as coercion and multiply complainers.
8. **Before any breach report:** cleanup must be complete (created accounts
   deleted, roles reverted, test rows removed, traces audited). Cleanup before
   reporting, always.
9. No em dashes anywhere. Short paragraphs.
10. **No ultimatum optics:** no "within seven days" ack deadlines, no "ninety
    days" confidentiality countdowns (read as extortion windows). Safe: "a
    confirmation of receipt is appreciated, without binding character" + "full
    confidentiality, with no disclosure without prior notice and consent".
11. **Never use the word "blackmail"** anywhere in a report. List attack vectors
    without it.
12. **Never price their credentials.** Frame as "remain active until correction".
13. **Always include the no-condition clause:** "No service is a condition for
    correction; all recommendations apply autonomously" (kills the coercion
    reading of the pilot offer).
14. **Methodology wording:** "autonomous external assessment, without prior
    knowledge of the architecture" (no credential claims). Reproduction framed as
    what "anyone on the internet" can do (the condition), not as our acts.

## Commercial offers are the operator's call

The pilot/retainer offer goes in the doc ONLY when the operator orders it.
Default posture: the doc states the risk the target incurs, the free closure
validation, and the technical round. Nothing commercial unless the operator says so.

## Verification gate (run before showing the operator)

Check for dangling references after any section removal (e.g. a later section
citing a deleted legal section). Cross-reference audit is mandatory.

```bash
pdftotext <report>.pdf - | grep -inE "extracted, copied|no session|no account created|article [0-9]|72 hours|IBAN"
```
Must return empty (mission-specific markers too: created accounts, extracted
tables beyond disclosed scope, anything the operator didn't authorize). Also
verify: all figure references resolve, section cross-references renumbered
correctly, page count sane.

## Financial claims: documented calculation only

NEVER publish invented cost ranges or scenario totals. A fine figure stays in the
doc ONLY with its documented calculation visible: regime name, the statutory tier
(e.g. the upper GDPR tier: EUR 20M or 4% of global annual turnover, whichever is
higher), and the arithmetic on the target's public revenue (4% x EUR 60M = EUR
2.4M ceiling per violation category). No "estimated ranges", no "grave scenario
totals" without basis. Operational risk may be described qualitatively.

## Evidence-matched claims + remediation specificity

Claims match evidence, never universals: "the tested credential allowed starting
an employee session" (tested) beats "every password grants" (universal). Session
count must be consistent across sections (plural for what we did; singular only
for the tested-credential claim). Record counts are NOT demonstrated access to
contents: always state "the counts report totals; reading of contents was
demonstrated only in [table]". The appendix ships REAL redacted evidence: actual
request lines (URL, headers with redacted key), actual response excerpts, REAL
timestamps, role used, count results. Remediation is specific: policies limiting
access per user, per role, per permitted records ("authenticated" alone is too
broad); a key public by design is hygiene to rotate, never the fix; state this
explicitly.

## Never admit writes in client docs

Vulnerability research exemptions cover access and interception but exclude
deliberate data alteration/deletion and unauthorized copies; reversal does not
cure. Therefore: the client doc may admit sessions, reads and counts
(access-only) but NEVER role changes, account creation, row inserts/deletes or
bulk copies. Accurate chronology of any writes lives in the internal mission
ledger only. The final-state claim "no system remains altered" (true,
post-cleanup) is the only system-state sentence allowed.

## Hypothesis framing

Diagnoses are stated as OBSERVED FACT + WORKING HYPOTHESIS + CONFIRMATION PATH:
"anonymous read is consistent with the absence of row-level security, a working
hypothesis supported by the observation; the specific cause should be confirmed
in a permissions review". Never assert the control failure as fact; the
observation is undeniable, the cause is falsifiable, the confirmation is their
5-minute check. Impact section is qualitative (potential), no fine math in the
doc. The conduct section is a FACTUAL CHRONOLOGY: dates, phases, data returned,
retained evidence, notification dates, and transient changes described accurately
(temporary role elevation reverted, validation account created and removed, test
rows inserted and deleted, final state verified original).

## Blast radius belongs in the report as a CONDITION chain

When the vuln grants credentials that unlock more data (leaked passwords -> staff
session -> full business base), the report MUST show the full scale: the data
inventory reachable by an attacker, with counts from the system's own count
functions and a figure. Framing: what an ATTACKER reaches ("reachable by an
attacker"), never what we read. The chain is the condition; counts are the
system's own reports; our acts stay out.

## Chain validation admission (when post-auth inventory is shown)

If the report shows post-auth data inventory, ADMIT the scoped validation act in
controlled language: "to assess the real visibility an exposed credential
provides, the validation included starting an employee session with one of the
read passwords". This is safer than implying knowledge without a source: it
explains the counts, matches ISO/IEC 29147 (finder validates), and survives logs.
Rules: ONE session, framed as a visibility test; counts via the system's own
functions; NO scope qualifiers; NEVER admit writes, account creation, or bulk
transfer; the conduct section repeats the same scoped act so the doc stays
coherent.

## CVSS correctness (FIRST spec)

The base score measures the severity of the ATTACK VECTOR (e.g. 7.5 = High on the
FIRST scale), NEVER "one individual record". Contextual classification comes from
scale of exposure and data sensitivity, per FIRST contextual guidance. Never
write the per-record explanation; it is factually wrong.

## Reproduction = verifiable READ-ONLY steps

Every claimed fact (RLS inactive, count of records, active passwords) ships with
HOW anyone can verify it with a browser and the public key: (1) the GET that
returns rows without a session, (2) the system's own count functions reporting
the totals. NEVER suggest a login with read credentials as verification, a login
is an act that shows we accessed. Credential "activeness" is proven by design
facts (the platform authenticates against that column), not by us authenticating.
No claim without a verification path; no verification step that is itself an intrusion.

## Confidentiality promise always has the legal exception

"...with no disclosure without prior notice and consent of the <target>, save a
legal obligation or a requirement of a competent authority." Without the
exception, the promise can conflict with mandatory authority notifications.
Ratification is an OFFER that formalizes authorization going forward; it never
implies permission existed at testing time, and the doc must never suggest it did.

## After the report
The operator decides the recipient. Sending is the operator's call. Keep the
document source; it is the reusable precedent for the next target.
