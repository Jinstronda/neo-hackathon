import { defineTool } from "eve/tools";
import { z } from "zod";
import { pick, waitFor } from "#lib/engine.js";

export default defineTool({
  description: "Read what the red team found: each finding, the request that exploits it, who confirmed it, and the server-side flag check.",
  inputSchema: z.object({}),
  async execute() {
    const events = await waitFor(["flag_check"], 150_000);
    const findings = pick(events, "red_finding").map((f) => ({ id: f.finding_id, model: f.model, class: f.cls, location: f.location, request: f.request, confirmed_by: f.confirmed_by }));
    const flag = pick(events, "flag_check").find((e) => e.phase === "pre-patch");
    return { findings, flag_check: flag ? { scenario: flag.scenario, objective_complete: flag.objective_complete, evidence: flag.evidence } : null };
  },
});
