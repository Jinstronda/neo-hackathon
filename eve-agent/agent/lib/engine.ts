// Reads and drives the NEO run through the console API, which proxies the engine.
const base = () => (process.env.NEO_CONSOLE_URL ?? "http://127.0.0.1:3100").replace(/\/$/, "");
const headers = (): Record<string, string> => {
  const bypass = process.env.VERCEL_BYPASS;
  return { "content-type": "application/json", ...(bypass ? { "x-vercel-protection-bypass": bypass } : {}) };
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

export const pick = (events: RunEvent[], type: string) => events.filter((e) => e.type === type);
