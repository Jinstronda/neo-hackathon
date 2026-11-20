import { loadRun } from '@/lib/engine';
import { phaseOf } from '@/lib/types';

export const dynamic = 'force-dynamic';

// Streams one phase of the run as Server-Sent Events. Real gaps between events are kept in order
// and compressed to 0.5-2.4 s so the stage sees each step land.
export async function GET(request: Request) {
  const phase = new URL(request.url).searchParams.get('phase') || 'all';
  const { events, source } = await loadRun();
  const chosen = events.filter((event) => phase === 'all' || phaseOf(event) === phase);
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      controller.enqueue(encoder.encode(`event: source\ndata: ${JSON.stringify({ source })}\n\n`));
      for (let index = 0; index < chosen.length; index += 1) {
        const gap = index ? chosen[index].ts - chosen[index - 1].ts : 0;
        await new Promise((resolve) => setTimeout(resolve, index ? Math.min(2400, Math.max(500, gap * 40)) : 300));
        if (request.signal.aborted) return;
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(chosen[index])}\n\n`));
      }
      controller.enqueue(encoder.encode('event: done\ndata: {}\n\n'));
      controller.close();
    },
  });
  return new Response(stream, { headers: { 'content-type': 'text/event-stream', 'cache-control': 'no-cache, no-transform' } });
}
