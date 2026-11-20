// Shared types + client-safe helpers (no fs, importable anywhere).

export type Agent = {
  id: string;
  role: "red" | "blue" | "reviewer";
  label: string;
  status: string;
  task?: string;
};

export type Step = {
  key: string;
  title: string;
  live: boolean;
  events: string[];
};

export type Metrics = {
  minutes_exploit_to_fix: number;
  cost_usd: number;
  where: string;
  tested_surface: number;
  untested_surface: number;
  regression_tests: number;
};

export type RunSummary = {
  id: string;
  title: string;
  date: string;
  where: string;
  agents: Agent[];
  steps: Step[];
  metrics: Metrics;
};

export type RunEvent = { type: string; ts: number; [k: string]: unknown };

export type Run = { run: RunSummary; events: RunEvent[]; source: "engine" | "fixture" };

export function hhmmss(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: "Europe/Lisbon",
  });
}

export function eventsForStep(step: Step, events: RunEvent[]): RunEvent[] {
  return events.filter((e) => step.events.includes(e.type));
}

// The retest gate, decided server-side: pre-patch exploit works, post-patch dead.
export function flagPair(events: RunEvent[]) {
  const pre = events.find((e) => e.type === "flag_check" && e.phase === "pre-patch");
  const post = events.find((e) => e.type === "retest");
  return { pre, post };
}
