import { createOpenAICompatible } from "@ai-sdk/openai-compatible";
import { defineAgent } from "eve";

const homodeus = createOpenAICompatible({
  name: "homodeus",
  baseURL: process.env.NEO_GATEWAY_BASE ?? "https://mcp.homodeus.co/llm/v1",
  apiKey: process.env.HOMODEUS_API_KEY,
  headers: {
    "X-HomoDeus-Project": "neo-console",
    "X-HomoDeus-Description": "NEO operator chat: drives the red/blue self-healing loop on the hackathon demo app",
  },
  includeUsage: true,
});

// model id confirmed on the gateway /v1/models, 2026-11-20
export default defineAgent({
  model: homodeus(process.env.NEO_AGENT_MODEL ?? "gpt-6-luna"),
  modelContextWindowTokens: 128_000,
});
