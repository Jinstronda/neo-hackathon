import { defineTool } from "eve/tools";
import { z } from "zod";
import { act, pick, runEvents } from "#lib/engine.js";

export default defineTool({
  description: "Record the human approval and merge the patch PR. Call only when the operator says approved or merge.",
  inputSchema: z.object({}),
  async execute() {
    const run = await act("approve");
    const { events } = await runEvents();
    const merge = pick(events, "merge")[0];
    const metrics = pick(events, "metrics")[0];
    return { engine: run.detail, merged: Boolean(merge), pr: merge?.pr_number, minutes_exploit_to_fix: metrics?.minutes_exploit_to_fix, cost_usd: metrics?.cost_usd };
  },
});
