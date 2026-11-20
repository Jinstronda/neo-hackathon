import 'server-only';

// Client for the NEO Eve agent (eve-agent/), self-hosted on the organizer server.
const EVE_URL = (process.env.EVE_URL ?? 'http://127.0.0.1:2000').replace(/\/$/, '');
const auth = (): Record<string, string> => process.env.NEO_EVE_SECRET
  ? { authorization: `Basic ${Buffer.from(`neo:${process.env.NEO_EVE_SECRET}`).toString('base64')}` } : {};

type Fact = { type: string; scope?: { turnId?: string }; data?: Record<string, unknown> };
type Line = { facts?: Fact[]; progress?: { type: string; scope?: { turnId?: string }; data?: Record<string, unknown> } };
export type TurnEvent = { kind: 'text'; delta: string } | { kind: 'tool'; name: string } | { kind: 'tool-done'; name: string; ok: boolean } | { kind: 'end'; outcome: string };

const validId = (id?: string) => id && /^wrun_[A-Za-z0-9]+$/.test(id) ? id : undefined;

export async function send(rawId: string | undefined, message: string): Promise<{ sessionId: string; deliveryId: string }> {
  const sessionId = validId(rawId);
  const url = sessionId ? `${EVE_URL}/eve/v1/session/${sessionId}` : `${EVE_URL}/eve/v1/session`;
  const response = await fetch(url, { method: 'POST', headers: { 'content-type': 'application/json', ...auth() }, body: JSON.stringify({ message }), signal: AbortSignal.timeout(15000) });
  if (!response.ok) throw new Error(`eve answered ${response.status}`);
  const body = await response.json() as { sessionId?: string; deliveryId: string };
  return { sessionId: body.sessionId ?? sessionId!, deliveryId: body.deliveryId };
}

// Follows one delivery's turn on the session stream and yields only that turn's text and tool calls.
export async function* turn(rawId: string, deliveryId: string, signal: AbortSignal): AsyncGenerator<TurnEvent> {
  const sessionId = validId(rawId);
  if (!sessionId) throw new Error('bad session id');
  const response = await fetch(`${EVE_URL}/eve/v1/session/${sessionId}/stream`, { headers: auth(), signal });
  if (!response.ok || !response.body) throw new Error(`eve stream ${response.status}`);
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  const names = new Map<string, string>();
  const runs = new Set<string>(), reasoning = new Set<string>();
  let turnId: string | undefined, buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += value;
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const raw of lines) {
      if (!raw.trim()) continue;
      const line = JSON.parse(raw) as Line;
      // later deltas of a part carry only partId ("<runId>.<n>"); match them to this turn's model runs
      const progress = line.progress;
      if (progress?.type === 'content.delta') {
        const partId = String(progress.data?.partId ?? '');
        if (progress.data?.kind === 'reasoning') reasoning.add(partId);
        if (runs.has(partId.split('.')[0]) && !reasoning.has(partId)) yield { kind: 'text', delta: String(progress.data?.delta ?? '') };
      }
      for (const fact of line.facts ?? []) {
        const data = fact.data ?? {};
        if (fact.type === 'delivery.consumed' && data.deliveryId === deliveryId) turnId = String(data.turnId);
        if (!turnId || fact.scope?.turnId !== turnId) continue;
        if (fact.type === 'model.requested') runs.add(String(data.runId));
        if (fact.type === 'call.requested') {
          const name = String((data.capability as { name?: string })?.name ?? '');
          names.set(String(data.callId), name);
          yield { kind: 'tool', name };
        }
        if (fact.type === 'call.settled') yield { kind: 'tool-done', name: names.get(String(data.callId)) ?? '', ok: data.outcome === 'completed' };
        if (fact.type === 'turn.settled') { yield { kind: 'end', outcome: String(data.outcome) }; reader.cancel().catch(() => {}); return; }
      }
    }
  }
}
