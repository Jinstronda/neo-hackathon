// The NEO run contract (neo-hackathon/docs/RUN_SCHEMA.md and neo/journal.py). Client-safe.
export type Agent = { id: string; role: 'red' | 'blue' | 'reviewer'; label: string; status: string; task?: string };
export type Step = { key: string; title: string; live: boolean; events: string[] };
export type Metrics = {
  minutes_exploit_to_fix: number; cost_usd: number; where: string;
  tested_surface: number; untested_surface: number; regression_tests: number;
  lockin_before?: number; lockin_after?: number;
};
export type RunSummary = { id: string; title: string; date: string; where: string; agents: Agent[]; steps: Step[]; metrics: Metrics };
export type RunEvent = { type: string; ts: number; [key: string]: unknown };
export type Source = 'engine' | 'recorded' | 'fixture';
export type Run = { run: RunSummary; events: RunEvent[]; source: Source };

export const text = (value: unknown) => typeof value === 'string' ? value : value == null ? '' : String(value);
export const num = (value: unknown) => typeof value === 'number' ? value : Number(value) || 0;

export function clock(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'Europe/Lisbon' });
}

// red phase: what NEO does before anyone says "fix it"
export const redTypes = ['radar_match', 'twin_create', 'red_start', 'red_finding', 'flag_check'];
export type Phase = 'red' | 'blue' | 'merge';
export const phaseOf = (event: RunEvent): Phase => event.type === 'merge' ? 'merge' : redTypes.includes(event.type) && event.phase !== 'post-patch' ? 'red' : 'blue';
