"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { Run, RunEvent, Step } from "@/lib/types";

function pick(events: RunEvent[], type: string, p?: (e: RunEvent) => boolean) {
  return events.filter((e) => e.type === type && (!p || p(e)));
}

function Artifact({ step, events }: { step: Step; events: RunEvent[] }) {
  if (step.key === "radar") {
    const m = pick(events, "radar_match")[0];
    if (!m) return null;
    return (
      <div className="art">
        <div className="art-grid">
          <Field k="CVE" v={String(m.cve)} mono />
          <Field k="EPSS" v={`${Math.round(Number(m.epss) * 100)}%`} mono />
          <Field k="KEV" v={m.kev ? "listed" : "no"} />
          <Field k="Package" v={`${m.package} ${m.version}`} mono />
          <Field k="OSV" v={String(m.osv)} mono />
          <Field k="Reachable" v={m.reachable ? "yes, in our code path" : "no"} />
        </div>
      </div>
    );
  }
  if (step.key === "red") {
    const f = pick(events, "red_finding").find((e) => e.confirmed_by);
    const flag = pick(events, "flag_check", (e) => e.phase === "pre-patch")[0];
    if (!f) return null;
    return (
      <div className="art">
        <div className="art-line">
          <span className="mono">{String(f.cls)}</span>
          <span className="faint"> at </span>
          <span className="mono">{String(f.location)}</span>
          <span className="faint"> · found by {String(f.model)}, confirmed by {String(f.confirmed_by)}</span>
        </div>
        <pre className="code">{String(f.request)}</pre>
        <pre className="code code-out">{String(f.response)}</pre>
        {flag && (
          <div className="flag flag-red">
            <span className="flag-k faint">server-side flag check · {String(flag.scenario)}</span>
            <span className="flag-v redval">exploit works — objective complete</span>
          </div>
        )}
      </div>
    );
  }
  if (step.key === "blue") {
    const p = pick(events, "blue_patch")[0];
    if (!p) return null;
    return (
      <div className="art">
        <div className="art-line">
          PR <span className="mono">#{String(p.pr_number)}</span>
          <span className="faint"> · branch </span>
          <span className="mono">{String(p.branch)}</span>
        </div>
        <pre className="code code-diff">{String(p.diff)}</pre>
        <div className="commits">
          {(p.commits as { msg: string; kind: string }[]).map((c, i) => (
            <div className="commit" key={i}>
              <span className="mono faint">{c.kind}</span>
              <span className="dim">{c.msg}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }
  if (step.key === "review") {
    const revs = pick(events, "review");
    return (
      <div className="art art-reviews">
        {revs.map((r, i) => (
          <div className="review" key={i}>
            <div className="review-top">
              <span className="review-who mono">{String(r.reviewer)}</span>
              <span className={r.verdict === "approve" ? "greenval" : "redval"}>
                {String(r.verdict).replace("_", " ")}
              </span>
            </div>
            <div className="review-body dim">{String(r.comment)}</div>
            <div className="review-foot faint">re-ran its claim before posting</div>
          </div>
        ))}
      </div>
    );
  }
  if (step.key === "retest") {
    const dep = pick(events, "twin_deploy")[0];
    const rt = pick(events, "retest")[0];
    const t = pick(events, "tests")[0];
    return (
      <div className="art">
        {dep && (
          <div className="art-line dim">
            Fresh twin <span className="mono">{String(dep.twin_id)}</span> built from{" "}
            <span className="mono">{String(dep.image)}</span>, same exploit replayed
          </div>
        )}
        {rt && (
          <div className="flag flag-green">
            <span className="flag-k faint">server-side flag check · {String(rt.scenario)}</span>
            <span className="flag-v greenval">exploit dead — objective fails</span>
          </div>
        )}
        {t && (
          <div className="art-line">
            Tests <span className="greenval mono">{String(t.passed)}/{String(t.total)}</span>
            <span className="faint"> pass · +{String(t.regression_added)} regression locked in</span>
          </div>
        )}
      </div>
    );
  }
  if (step.key === "merge") {
    const m = pick(events, "merge")[0];
    if (!m) return null;
    return (
      <div className="art art-merge">
        <div className="merge-gate dim">
          The gate: merge is possible only now — exploit fails and tests pass.
        </div>
        <div className="art-line">
          PR <span className="mono">#{String(m.pr_number)}</span> merged by{" "}
          <span>{String(m.by)}</span>
          <span className="faint"> · approved by {(m.approved_by as string[]).join(" + ")}</span>
        </div>
      </div>
    );
  }
  return null;
}

function Field({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="field">
      <span className="field-k faint">{k}</span>
      <span className={`field-v ${mono ? "mono" : ""}`}>{v}</span>
    </div>
  );
}

export default function LoopViewer({ data }: { data: Run }) {
  const { run, events } = data;
  const steps = run.steps;
  const [i, setI] = useState(0);
  const [playing, setPlaying] = useState(false);
  const step = steps[i];

  useEffect(() => {
    if (!playing) return;
    if (i >= steps.length - 1) {
      setPlaying(false);
      return;
    }
    const t = setTimeout(() => setI((n) => Math.min(n + 1, steps.length - 1)), 2600);
    return () => clearTimeout(t);
  }, [playing, i, steps.length]);

  return (
    <section className="view">
      <div className="title-row">
        <h1 className="title">The loop</h1>
        <div className="loop-controls">
          <button className="ctl" onClick={() => setI((n) => Math.max(0, n - 1))} disabled={i === 0}>
            ‹ prev
          </button>
          <button
            className="ctl ctl-play"
            onClick={() => {
              if (i >= steps.length - 1) setI(0);
              setPlaying((p) => !p);
            }}
          >
            {playing ? "❚❚ pause" : "▶ play"}
          </button>
          <button
            className="ctl"
            onClick={() => setI((n) => Math.min(steps.length - 1, n + 1))}
            disabled={i === steps.length - 1}
          >
            next ›
          </button>
        </div>
      </div>

      <ol className="stepper">
        {steps.map((s, n) => (
          <li
            key={s.key}
            className={`step-chip ${n === i ? "on" : ""} ${n < i ? "past" : ""}`}
            onClick={() => {
              setPlaying(false);
              setI(n);
            }}
          >
            <span className="step-chip-idx mono">{n + 1}</span>
            <span className="step-chip-label">{s.title}</span>
          </li>
        ))}
      </ol>

      <AnimatePresence mode="wait">
        <motion.div
          key={step.key}
          className="loop-panel"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
        >
          <div className="loop-panel-head">
            <span className={`loop-panel-title ${step.live ? "live-caret" : ""}`}>{step.title}</span>
            <span className="loop-tag mono faint">{step.live ? "live" : "recorded"}</span>
          </div>
          <Artifact step={step} events={events} />
        </motion.div>
      </AnimatePresence>
    </section>
  );
}
