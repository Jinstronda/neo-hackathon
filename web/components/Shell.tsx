"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { Run } from "@/lib/types";
import AgentBoard from "./AgentBoard";
import Timeline from "./Timeline";
import LoopViewer from "./LoopViewer";
import Infra from "./Infra";
import Numbers from "./Numbers";
import Chat from "./Chat";

const VIEWS = [
  { key: "board", label: "Swarm", hint: "the agents" },
  { key: "loop", label: "The loop", hint: "find → prove → fix" },
  { key: "timeline", label: "Incident", hint: "exploit → fixed" },
  { key: "numbers", label: "Numbers", hint: "surface, cost, EU" },
  { key: "infra", label: "Infra & log", hint: "live stream" },
  { key: "chat", label: "Ask NEO", hint: "about this run" },
] as const;

type ViewKey = (typeof VIEWS)[number]["key"];

export default function Shell({ data }: { data: Run }) {
  const [view, setView] = useState<ViewKey>("board");
  const { run } = data;

  return (
    <div className="shell">
      <aside className="rail">
        <div className="brand">
          <span className="brand-mark">NEO</span>
          <span className="brand-sub faint">proof before merge</span>
        </div>
        <nav>
          {VIEWS.map((v, i) => (
            <button
              key={v.key}
              className={`nav-item ${view === v.key ? "on" : ""}`}
              onClick={() => setView(v.key)}
            >
              <span className="nav-idx mono faint">{String(i + 1).padStart(2, "0")}</span>
              <span className="nav-body">
                <span className="nav-label">{v.label}</span>
                <span className="nav-hint faint">{v.hint}</span>
              </span>
            </button>
          ))}
        </nav>
        <div className="rail-foot faint mono">
          <div>{run.id}</div>
          <div>{run.date}</div>
          <div>{data.source === "engine" ? "live engine run" : "recorded fixture"}</div>
        </div>
      </aside>

      <main className="stage">
        <AnimatePresence mode="wait">
          <motion.div
            key={view}
            className="stage-inner"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          >
            {view === "board" && <AgentBoard data={data} />}
            {view === "loop" && <LoopViewer data={data} />}
            {view === "timeline" && <Timeline data={data} />}
            {view === "numbers" && <Numbers data={data} />}
            {view === "infra" && <Infra data={data} />}
            {view === "chat" && <Chat />}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}
