"use client";

import { motion } from "framer-motion";
import type { Run, RunEvent } from "@/lib/types";
import { hhmmss } from "@/lib/types";

type Row = { ts: number; head: string; detail: string; tone?: "red" | "green" };

function rows(events: RunEvent[]): Row[] {
  const byType = (t: string, p?: (e: RunEvent) => boolean) =>
    events.find((e) => e.type === t && (!p || p(e)));
  const r: (Row | null)[] = [
    byType("radar_match") && {
      ts: byType("radar_match")!.ts,
      head: "Radar match",
      detail: `${byType("radar_match")!.cve} matched our SBOM (${byType("radar_match")!.package} ${byType("radar_match")!.version}), reachable`,
    },
    byType("flag_check", (e) => e.phase === "pre-patch") && {
      ts: byType("flag_check", (e) => e.phase === "pre-patch")!.ts,
      head: "Exploit proven",
      detail: "server-side flag check: exploit works on the twin",
      tone: "red" as const,
    },
    byType("blue_patch") && {
      ts: byType("blue_patch")!.ts,
      head: "Patch PR opened",
      detail: `#${byType("blue_patch")!.pr_number} — fix plus a regression test`,
    },
    byType("review", (e) => e.reviewer === "security") && {
      ts: byType("review", (e) => e.reviewer === "security")!.ts,
      head: "Security review",
      detail: "re-ran the exploit against the diff — approve",
    },
    byType("review", (e) => e.reviewer === "correctness") && {
      ts: byType("review", (e) => e.reviewer === "correctness")!.ts,
      head: "Correctness review",
      detail: "re-ran the suite against the diff — approve",
    },
    byType("retest") && {
      ts: byType("retest")!.ts,
      head: "Exploit replayed on patch",
      detail: "server-side flag check: exploit dead, tests green",
      tone: "green" as const,
    },
    byType("merge") && {
      ts: byType("merge")!.ts,
      head: "Human merges",
      detail: `approved by ${(byType("merge")!.approved_by as string[]).join(" + ")}`,
    },
  ];
  return r.filter(Boolean) as Row[];
}

export default function Timeline({ data }: { data: Run }) {
  const list = rows(data.events);
  const mins = data.run.metrics.minutes_exploit_to_fix;

  return (
    <section className="view">
      <h1 className="title">Incident</h1>
      <div className="tl-wrap">
        <div className="tl-hero">
          <div className="tl-hero-num mono">
            {mins}
            <span className="tl-hero-unit faint">min</span>
          </div>
          <div className="tl-hero-cap dim">
            exploit proven <span className="redval">red</span> to verified fix{" "}
            <span className="greenval">green</span>, no one woke up
          </div>
        </div>
        <ol className="tl">
          {list.map((row, i) => (
            <motion.li
              className="tl-row"
              key={i}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.05 * i, duration: 0.28 }}
            >
              <span className="tl-time mono faint">{hhmmss(row.ts)}</span>
              <span className="tl-stem" aria-hidden />
              <span className="tl-body">
                <span
                  className={`tl-head ${row.tone === "red" ? "redval" : row.tone === "green" ? "greenval" : ""}`}
                >
                  {row.head}
                </span>
                <span className="tl-detail dim">{row.detail}</span>
              </span>
            </motion.li>
          ))}
        </ol>
      </div>
    </section>
  );
}
