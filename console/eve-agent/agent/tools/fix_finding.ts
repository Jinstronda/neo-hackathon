import { defineTool } from "eve/tools";
import { z } from "zod";
import { act, pick, waitFor } from "#lib/engine.js";

export default defineTool({
  description: "Have the blue agent patch the finding: the patch goes up, two reviewers from different vendors check the diff, the twin is rebuilt and the exploit replayed. Returns the patch (PR number only when a real PR exists), reviews, retest and tests.",
  inputSchema: z.object({}),
  async execute() {
    const run = await act("fix");
    const events = await waitFor(["retest", "tests", "review"], 240_000);
    const patch = pick(events, "blue_patch")[0];
    const retest = pick(events, "retest")[0];
    const tests = pick(events, "tests")[0];
    return {
      engine: run.detail,
      patch: patch ? { pr_number: String(patch.pr_url ?? "").startsWith("https://github.com/Jinstronda/") ? patch.pr_number ?? null : null, branch: patch.branch } : null,
      reviews: pick(events, "review").map((r) => ({ reviewer: r.reviewer, verdict: r.verdict })),
      retest: retest ? { objective_complete: retest.objective_complete, status: retest.status } : null,
      tests: tests ? { passed: tests.passed, total: tests.total } : null,
    };
  },
});
