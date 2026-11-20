"use client";

import { useEffect, useRef, useState } from "react";
import type { Run, RunEvent } from "@/lib/types";
import { hhmmss } from "@/lib/types";

function line(e: RunEvent): string {
  switch (e.type) {
    case "radar_match":
      return `radar  ${e.cve} matched ${e.package}@${e.version} (epss ${e.epss})`;
    case "twin_create":
      return `twin   created ${e.twin_id} on ${e.where} from ${e.image}`;
    case "red_start":
      return `red    swarm started on ${e.twin_id}: ${(e.models as string[]).join(", ")}`;
    case "red_finding":
      return `red    ${e.model} → ${e.cls} at ${e.location} (confirmed by ${e.confirmed_by})`;
    case "flag_check":
      return `flag   ${e.phase} ${e.scenario}: objective_complete=${e.objective_complete}`;
    case "blue_patch":
      return `blue   PR #${e.pr_number} opened on ${e.branch}`;
    case "review":
      return `review ${e.reviewer} (${e.vendor}) → ${e.verdict}, rechecked=${e.rechecked}`;
    case "twin_deploy":
      return `twin   redeployed ${e.twin_id} with patch ${e.image}`;
    case "retest":
      return `retest ${e.scenario}: objective_complete=${e.objective_complete} → ${e.status}`;
    case "tests":
      return `tests  ${e.passed}/${e.total} pass (+${e.regression_added} regression)`;
    case "metrics":
      return `metrics ${e.minutes_exploit_to_fix}min · $${e.cost_usd} · ${e.where}`;
    case "merge":
      return `merge  PR #${e.pr_number} merged by ${e.by}`;
    default:
      return `${e.type}`;
  }
}

function tone(e: RunEvent): string {
  if (e.type === "flag_check" && e.phase === "pre-patch") return "redval";
  if (e.type === "retest" || e.type === "merge" || e.type === "tests") return "greenval";
  return "";
}

export default function Infra({ data }: { data: Run }) {
  const [log, setLog] = useState<RunEvent[]>([]);
  const [streaming, setStreaming] = useState(true);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const es = new EventSource("/api/stream");
    es.onmessage = (m) => setLog((l) => [...l, JSON.parse(m.data)]);
    es.addEventListener("done", () => {
      setStreaming(false);
      es.close();
    });
    es.onerror = () => {
      setStreaming(false);
      es.close();
    };
    return () => es.close();
  }, []);

  useEffect(() => {
    if (boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight;
  }, [log]);

  const infra = [
    { k: "Where it runs", v: "EU data center, our own servers" },
    { k: "Models", v: "open-weight, no data leaves the region" },
    { k: "Twin", v: "disposable full copy of the app, per PR" },
    { k: "Gateway", v: "every model call traced through one boundary" },
    { k: "Writes", v: "read-only by default, each write a human approves" },
    { k: "Decision", v: "server-side flag checks, never an agent's claim" },
  ];

  return (
    <section className="view">
      <h1 className="title">Infra & log</h1>
      <div className="infra">
        <div className="infra-grid">
          {infra.map((x) => (
            <div className="infra-cell" key={x.k}>
              <span className="infra-k faint">{x.k}</span>
              <span className="infra-v">{x.v}</span>
            </div>
          ))}
        </div>
        <div className="logwrap">
          <div className="log-head">
            <span className="log-title">event stream</span>
            <span className={`log-state faint mono ${streaming ? "live-caret" : ""}`}>
              {streaming ? "streaming" : "done"}
            </span>
          </div>
          <div className="log" ref={boxRef}>
            {log.map((e, i) => (
              <div className="log-row mono" key={i}>
                <span className="log-ts faint">{hhmmss(e.ts)}</span>
                <span className={`log-msg ${tone(e)}`}>{line(e)}</span>
              </div>
            ))}
            {log.length === 0 && <div className="faint mono">connecting…</div>}
          </div>
        </div>
      </div>
    </section>
  );
}
