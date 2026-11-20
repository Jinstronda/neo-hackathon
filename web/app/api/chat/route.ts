import { createOpenAI } from "@ai-sdk/openai";
import { streamText, convertToCoreMessages, type Message } from "ai";
import { loadRun } from "@/lib/run";
import { ensureGatewayKey } from "@/lib/serverEnv";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

const GATEWAY_BASE = process.env.NEO_GATEWAY_BASE || "https://mcp.homodeus.co/llm/v1";

export async function POST(req: Request) {
  const key = await ensureGatewayKey();
  if (!key) {
    return new Response("HOMODEUS_API_KEY not set", { status: 503 });
  }

  const { messages }: { messages: Message[] } = await req.json();

  // Ground the chat in the real run so answers cite what happened.
  const { run, events } = await loadRun();
  const context = JSON.stringify({ summary: run, events }).slice(0, 24000);

  const gateway = createOpenAI({
    baseURL: GATEWAY_BASE,
    apiKey: key,
    headers: {
      "X-HomoDeus-Project": "neo-hackathon",
      "X-HomoDeus-Description": "NEO run explainer chat on the web UI",
    },
  });

  const result = streamText({
    model: gateway("gpt-6-luna"),
    system:
      "You are NEO, an open-source agentic pentest framework. Answer questions about THIS run only, " +
      "grounded in the run artifact below. Be terse and factual. Server-side flag checks decide red/green, " +
      "never an agent's own claim. The offensive models are shown only as model-1, model-2, model-3. " +
      "Today is 2026-11-20.\n\nRUN ARTIFACT:\n" +
      context,
    messages: convertToCoreMessages(messages),
    temperature: 0.2,
  });

  return result.toDataStreamResponse();
}
