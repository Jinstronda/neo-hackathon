import { defineTool } from "eve/tools";
import { z } from "zod";
import { act, pick, runEvents } from "#lib/engine.js";

export default defineTool({
  description: "Start the NEO red team against a disposable twin of our own demo app. Returns the twin and the attacking models.",
  inputSchema: z.object({}),
  async execute() {
    const started = await act("attack");
    const { events, source } = await runEvents();
    const twin = pick(events, "twin_create")[0];
    const red = pick(events, "red_start")[0];
    return { started: true, engine: started.detail, source, twin: twin?.twin_id, where: twin?.where, models: red?.models ?? [] };
  },
});
