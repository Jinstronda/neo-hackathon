import 'server-only';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { honest } from './honest';
import type { Run } from './types';

// The NEO engine (neo-hackathon) owns runs. ENGINE_URL points at its API; without it the console
// reads the newest bundled run: a recorded engine run when one is checked in, the fixture otherwise.
const ENGINE_URL = process.env.ENGINE_URL?.replace(/\/$/, '');
const auth = (): Record<string, string> => process.env.NEO_EVE_SECRET
  ? { authorization: `Basic ${Buffer.from(`neo:${process.env.NEO_EVE_SECRET}`).toString('base64')}` } : {};

export async function bundled(): Promise<Run> {
  for (const [file, source] of [['demo-run.json', 'recorded'], ['fixture.json', 'fixture']] as const) {
    try {
      const data = JSON.parse(await readFile(path.join(process.cwd(), 'public', 'runs', file), 'utf8'));
      return honest({ run: data.run, events: data.events, source });
    } catch { /* next */ }
  }
  throw new Error('no run available');
}

// live engine only for a signed-in operator; everyone else gets the recorded run (replay)
export async function loadRun(live = false): Promise<Run> {
  if (live && ENGINE_URL) {
    try {
      const response = await fetch(`${ENGINE_URL}/api/run`, { cache: 'no-store', headers: auth(), signal: AbortSignal.timeout(6000) });
      if (response.ok) { const data = await response.json(); return honest({ run: data.run, events: data.events, source: data.source === 'fixture' ? 'fixture' : 'engine' }); }
    } catch { /* engine unreachable: fall back */ }
  }
  return bundled();
}

// asks the engine to act; returns false when the engine has no live endpoint, so the console replays the recorded run
export async function engineAction(action: 'attack' | 'fix' | 'approve'): Promise<{ live: boolean; detail: string }> {
  if (!ENGINE_URL) return { live: false, detail: 'replaying the recorded run' };
  try {
    const response = await fetch(`${ENGINE_URL}/api/run`, {
      method: 'POST', headers: { 'content-type': 'application/json', ...auth() }, body: JSON.stringify({ action }), signal: AbortSignal.timeout(15000),
    });
    return { live: response.ok, detail: response.ok ? 'engine accepted' : `engine answered ${response.status}` };
  } catch (error) {
    return { live: false, detail: `engine unreachable: ${error instanceof Error ? error.name : 'error'}` };
  }
}
