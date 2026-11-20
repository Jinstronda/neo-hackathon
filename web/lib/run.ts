// The ONE place the UI loads a run from. Default: the bundled fixture.
// The Integrate step points at the real engine output with a single env var:
//   NEO_RUN_DIR=../runs/demo-run
// then this reads <dir>/run.json + <dir>/events.jsonl instead of the fixture.
import { promises as fs } from "fs";
import path from "path";
import type { Run } from "./types";

const FIXTURE = path.join(process.cwd(), "public", "fixture-run.json");

export async function loadRun(): Promise<Run> {
  const dir = process.env.NEO_RUN_DIR;
  if (dir) {
    try {
      const base = path.isAbsolute(dir) ? dir : path.join(process.cwd(), dir);
      const run = JSON.parse(await fs.readFile(path.join(base, "run.json"), "utf8"));
      const raw = await fs.readFile(path.join(base, "events.jsonl"), "utf8");
      const events = raw
        .split("\n")
        .filter((l) => l.trim())
        .map((l) => JSON.parse(l));
      return { run, events, source: "engine" };
    } catch {
      // Engine output not there yet, fall through to the fixture.
    }
  }
  const fx = JSON.parse(await fs.readFile(FIXTURE, "utf8"));
  return { run: fx.run, events: fx.events, source: "fixture" };
}
