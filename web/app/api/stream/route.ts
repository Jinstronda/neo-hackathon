import { loadRun } from "@/lib/run";

export const dynamic = "force-dynamic";

// Replays the run's events as a Server-Sent Events stream, paced so the log
// fills live on screen. The engine run and the fixture stream the same way.
export async function GET() {
  const { events } = await loadRun();
  const enc = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      for (const ev of events) {
        controller.enqueue(enc.encode(`data: ${JSON.stringify(ev)}\n\n`));
        await new Promise((r) => setTimeout(r, 650));
      }
      controller.enqueue(enc.encode("event: done\ndata: {}\n\n"));
      controller.close();
    },
  });
  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
