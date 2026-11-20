// Reads and drives the NEO run: the engine runner on this box when NEO_ENGINE_URL is set,
// otherwise the console API (which serves the recorded run).
const base = () => (process.env.NEO_ENGINE_URL ?? process.env.NEO_CONSOLE_URL ?? "http://127.0.0.1:3100").replace(/\/$/, "");
const headers = (): Record<string, string> => {
  const bypass = process.env.VERCEL_BYPASS, secret = process.env.NEO_EVE_SECRET;
  return {
    "content-type": "application/json",
    ...(bypass ? { "x-vercel-protection-bypass": bypass } : {}),
    ...(process.env.NEO_ENGINE_URL && secret ? { authorization: `Basic ${Buffer.from(`neo:${secret}`).toString("base64")}` } : {}),
  };
};

export type RunEvent = { type: string; ts: number; [key: string]: unknown };

export async function runEvents(): Promise<{ source: string; events: RunEvent[] }> {
  const response = await fetch(`${base()}/api/run`, { headers: headers(), signal: AbortSignal.timeout(10_000) });
  if (!response.ok) throw new Error(`console answered ${response.status}`);
  const data = (await response.json()) as { source: string; events: RunEvent[] };
  return { source: data.source, events: data.events };
}

export async function act(action: "attack" | "fix" | "approve"): Promise<{ live: boolean; detail: string }> {
  const response = await fetch(`${base()}/api/run`, { method: "POST", headers: headers(), body: JSON.stringify({ action }), signal: AbortSignal.timeout(20_000) });
  if (!response.ok) throw new Error(`console answered ${response.status}`);
  return (await response.json()) as { live: boolean; detail: string };
}

// the cloud run lands findings and the retest after the harness finishes; wait for them
export async function waitFor(types: string[], timeoutMs: number): Promise<RunEvent[]> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const { events } = await runEvents();
    if (types.every((t) => events.some((e) => e.type === t)) || Date.now() > deadline) return events;
    await new Promise((resolve) => setTimeout(resolve, 2500));
  }
}

export const pick = (events: RunEvent[], type: string) => events.filter((e) => e.type === type);
