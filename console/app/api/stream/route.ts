import { loadRun } from '@/lib/engine';
import { type Phase, type RunEvent } from '@/lib/types';
import { operator } from '@/lib/session';

export const dynamic = 'force-dynamic';
export const maxDuration = 300;

// a phase is over once its last event lands; a live cloud run gets there after the harness finishes
const terminal: Record<Phase, string[]> = { red: ['flag_check', 'harness_error'], blue: ['metrics'], merge: ['merge', 'merge_ready'] };
// red is everything before the patch, merge is the human gate, blue is the rest (works for live and recorded runs)
function phaseEvents(events: RunEvent[], phase: Phase): RunEvent[] {
  const merge = (e: RunEvent) => e.type === 'merge' || e.type === 'merge_ready';
  const cut = events.findIndex((e) => e.type === 'blue_patch');
  const red = cut < 0 ? events.filter((e) => !merge(e)) : events.slice(0, cut);
  if (phase === 'red') return red;
  if (phase === 'merge') return events.filter(merge);
  return cut < 0 ? [] : events.slice(cut).filter((e) => !merge(e));
}
// events of one batch can share a timestamp (three retests at once), so the whole event is the key
const key = (e: RunEvent) => JSON.stringify(e);

// Streams one phase as Server-Sent Events. Polls the engine so live events arrive as they land;
// real gaps between events are kept in order and compressed to 0.5-2.4 s for the stage.
export async function GET(request: Request) {
  const asked = new URL(request.url).searchParams.get('phase');
  const phase: Phase = asked === 'blue' || asked === 'merge' ? asked : 'red';
  const live = Boolean(await operator());
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      const sent = new Set<string>();
      let last: RunEvent | undefined, done = false;
      const deadline = Date.now() + 280_000;
      while (!done && Date.now() < deadline && !request.signal.aborted) {
        const { events, source } = await loadRun(live);
        if (!sent.size) controller.enqueue(encoder.encode(`event: source\ndata: ${JSON.stringify({ source })}\n\n`));
        const mine = phaseEvents([...events].sort((a, b) => a.ts - b.ts), phase);
        for (const event of mine) {
          if (sent.has(key(event))) continue;
          const gap = last ? event.ts - last.ts : 0;
          await new Promise((resolve) => setTimeout(resolve, last ? Math.min(2400, Math.max(500, gap * 40)) : 300));
          if (request.signal.aborted) return;
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
          sent.add(key(event)); last = event;
          if (source === 'engine' && terminal[phase].includes(event.type)) done = true;
        }
        // a recorded run is complete: the phase ends once its last event is out
        if (source !== 'engine' && mine.every((e) => sent.has(key(e)))) done = true;
        if (!done) await new Promise((resolve) => setTimeout(resolve, 2000));
      }
      controller.enqueue(encoder.encode('event: done\ndata: {}\n\n'));
      controller.close();
    },
  });
  return new Response(stream, { headers: { 'content-type': 'text/event-stream', 'cache-control': 'no-cache, no-transform' } });
}
