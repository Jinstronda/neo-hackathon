"use client";

import { motion } from "framer-motion";
import type { Run, RunEvent } from "@/lib/types";

function redFinding(events: RunEvent[], label: string): RunEvent | undefined {
  return events.find((e) => e.type === "red_finding" && e.model === label);
}

function reviewFor(events: RunEvent[], kind: string): RunEvent | undefined {
  return events.find((e) => e.type === "review" && e.reviewer === kind);
}

export default function AgentBoard({ data }: { data: Run }) {
  const { run, events } = data;
  const groups = [
    { role: "red", heading: "NEO — offensive swarm", note: "open-weight models on our own EU servers" },
    { role: "blue", heading: "Blue — the fix", note: "writes the patch, opens the PR" },
    { role: "reviewer", heading: "Review — two vendors", note: "each re-runs its claim before posting" },
  ] as const;

  return (
    <section className="view">
      <h1 className="title">The swarm</h1>
      <div className="board">
        {groups.map((g) => {
          const agents = run.agents.filter((a) => a.role === g.role);
          return (
            <div className="board-col" key={g.role}>
              <div className="board-head">
                <span className="board-head-label">{g.heading}</span>
                <span className="board-head-note faint">{g.note}</span>
              </div>
              <div className="cards">
                {agents.map((a, i) => {
                  const find = g.role === "red" ? redFinding(events, a.label) : undefined;
                  const rev = g.role === "reviewer" ? reviewFor(events, a.label) : undefined;
                  return (
                    <motion.div
                      className="card"
                      key={a.id}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.04 * i, duration: 0.3 }}
                    >
                      <div className="card-top">
                        <span className="card-name mono">{a.label}</span>
                        <span className="card-role faint">{a.role}</span>
                      </div>
                      <div className="card-task dim">{a.task}</div>
                      <div className="card-state">
                        {g.role === "red" && find && (
                          <span>
                            <span className="redval mono">{String(find.cls)}</span>
                            <span className="faint"> · confirmed by {String(find.confirmed_by)}</span>
                          </span>
                        )}
                        {g.role === "red" && !find && a.status === "done" && (
                          <span className="faint">swept, no new finding</span>
                        )}
                        {g.role === "blue" && (
                          <span className="dim">
                            PR <span className="mono">#{String(events.find((e) => e.type === "blue_patch")?.pr_number ?? "—")}</span> open with fix + regression test
                          </span>
                        )}
                        {g.role === "reviewer" && rev && (
                          <span>
                            <span className={rev.verdict === "approve" ? "greenval" : "redval"}>
                              {String(rev.verdict).replace("_", " ")}
                            </span>
                            <span className="faint"> · re-ran its claim</span>
                          </span>
                        )}
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
