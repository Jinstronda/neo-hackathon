import { defineTool } from "eve/tools";
import { z } from "zod";
import { act, pick, waitFor } from "#lib/engine.js";

export default defineTool({
  description: "Have the blue agent patch the finding: opens the PR, two reviewers re-run the exploit, the twin is rebuilt and the exploit replayed. Returns the PR, reviews, retest and tests.",
  inputSchema: z.object({}),
  async execute() {
    const run = await act("fix");
    const events = await waitFor(["retest", "tests", "review"], 240_000);
    const patch = pick(events, "blue_patch")[0];
    const retest = pick(events, "retest")[0];
    const tests = pick(events, "tests")[0];
    return {
      engine: run.detail,
      patch: patch ? { pr_number: patch.pr_number ?? null, branch: patch.branch } : null,
      reviews: pick(events, "review").map((r) => ({ reviewer: r.reviewer, verdict: r.verdict })),
      retest: retest ? { objective_complete: retest.objective_complete, status: retest.status } : null,
      tests: tests ? { passed: tests.passed, total: tests.total } : null,
    };
  },
});
