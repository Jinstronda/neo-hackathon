import { loadRun } from '@/lib/engine';
import { phaseOf, type Phase, type RunEvent } from '@/lib/types';

export const dynamic = 'force-dynamic';
export const maxDuration = 300;

// a phase is over once its last event lands; a live cloud run gets there after the harness finishes
const terminal: Record<Phase, string[]> = { red: ['flag_check', 'harness_error'], blue: ['metrics'], merge: ['merge'] };
const key = (e: RunEvent) => `${e.type}:${e.ts}`;

// Streams one phase as Server-Sent Events. Polls the engine so live events arrive as they land;
// real gaps between events are kept in order and compressed to 0.5-2.4 s for the stage.
export async function GET(request: Request) {
  const asked = new URL(request.url).searchParams.get('phase');
  const phase: Phase = asked === 'blue' || asked === 'merge' ? asked : 'red';
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      const sent = new Set<string>();
      let last: RunEvent | undefined, done = false;
      const deadline = Date.now() + 280_000;
      while (!done && Date.now() < deadline && !request.signal.aborted) {
        const { events, source } = await loadRun();
        if (!sent.size) controller.enqueue(encoder.encode(`event: source\ndata: ${JSON.stringify({ source })}\n\n`));
        for (const event of events.filter((e) => phaseOf(e) === phase || (phase === 'red' && e.type === 'harness_error'))) {
          if (sent.has(key(event))) continue;
          const gap = last ? event.ts - last.ts : 0;
          await new Promise((resolve) => setTimeout(resolve, last ? Math.min(2400, Math.max(500, gap * 40)) : 300));
          if (request.signal.aborted) return;
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
          sent.add(key(event)); last = event;
          if (terminal[phase].includes(event.type)) done = true;
        }
        if (!done) await new Promise((resolve) => setTimeout(resolve, 2000));
      }
      controller.enqueue(encoder.encode('event: done\ndata: {}\n\n'));
      controller.close();
    },
  });
  return new Response(stream, { headers: { 'content-type': 'text/event-stream', 'cache-control': 'no-cache, no-transform' } });
}
