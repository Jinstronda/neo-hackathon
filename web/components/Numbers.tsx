"use client";

import { motion } from "framer-motion";
import type { Run } from "@/lib/types";

export default function Numbers({ data }: { data: Run }) {
  const m = data.run.metrics;
  const tested = m.tested_surface;
  const untested = m.untested_surface;

  const figures = [
    { v: `${m.minutes_exploit_to_fix}`, unit: "min", cap: "exploit proven to verified fix" },
    { v: `$${m.cost_usd.toFixed(2)}`, unit: "", cap: "model cost for this full run" },
    { v: `${m.regression_tests}`, unit: "tests", cap: "attacks now replayed in CI forever" },
    { v: m.where, unit: "", cap: "code, logs and findings stay in region" },
  ];

  return (
    <section className="view">
      <h1 className="title">Numbers</h1>
      <div className="nums">
        <div className="figrow">
          {figures.map((f, i) => (
            <motion.div
              className="fig"
              key={f.cap}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.05 * i, duration: 0.3 }}
            >
              <div className="fig-v mono">
                {f.v}
                {f.unit && <span className="fig-unit faint"> {f.unit}</span>}
              </div>
              <div className="fig-cap dim">{f.cap}</div>
            </motion.div>
          ))}
        </div>

        <div className="surface">
          <div className="surface-head">
            <span className="surface-title">Attack surface under test</span>
            <span className="mono">
              <span className="greenval">{tested}%</span>
              <span className="faint"> tested · {untested}% not yet</span>
            </span>
          </div>
          <div className="surface-bar">
            <motion.div
              className="surface-fill"
              initial={{ width: 0 }}
              animate={{ width: `${tested}%` }}
              transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
            />
          </div>
          <div className="surface-note faint">
            Every fixed exploit becomes a permanent test, so this share only grows.
          </div>
        </div>
      </div>
    </section>
  );
}
