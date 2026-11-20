import { createDataStreamResponse, formatDataStreamPart } from 'ai';
import { cookies } from 'next/headers';
import { send, turn } from '@/lib/eve';
import { bundled } from '@/lib/engine';
import { replayTurn } from '@/lib/replay';
import { operator } from '@/lib/session';

export const dynamic = 'force-dynamic';
export const maxDuration = 120;

const actionOf: Record<string, string> = { attack_demo_app: 'attack', fix_finding: 'fix', approve_merge: 'approve' };
type Incoming = { messages?: { role: string; content: string }[] };

// The chat is an Eve agent session. Its text streams as AI SDK text; each tool call becomes a
// data part the console uses to start the matching engine phase on screen.
export async function POST(request: Request) {
  const { messages = [] } = await request.json().catch(() => ({})) as Incoming;
  const message = [...messages].reverse().find((m) => m.role === 'user')?.content?.trim();
  if (!message) return Response.json({ error: 'empty message' }, { status: 400 });
  if (!(await operator())) {
    // replay for visitors: same stream protocol, NEO's lines derived from the recorded run
    const { events } = await bundled();
    const step = replayTurn(message, events);
    return createDataStreamResponse({
      async execute(writer) {
        if (step.action) writer.writeData({ action: step.action });
        writer.write(formatDataStreamPart('tool_call', { toolCallId: `${step.tool}-${Date.now()}`, toolName: step.tool, args: {} }));
        for (const word of step.reply.split(/(?<= )/)) {
          writer.write(formatDataStreamPart('text', word));
          await new Promise((resolve) => setTimeout(resolve, 28));
        }
      },
    });
  }
  const jar = await cookies();
  const fresh = messages.filter((m) => m.role === 'user').length === 1;
  let session: { sessionId: string; deliveryId: string };
  try {
    session = await send(fresh ? undefined : jar.get('neo_session')?.value, message);
  } catch {
    session = await send(undefined, message).catch(() => ({ sessionId: '', deliveryId: '' }));
  }
  if (!session.sessionId) return Response.json({ error: 'NEO agent unreachable' }, { status: 502 });
  return createDataStreamResponse({
    headers: { 'set-cookie': `neo_session=${session.sessionId}; Path=/; HttpOnly; SameSite=Lax; Secure` },
    async execute(writer) {
      for await (const event of turn(session.sessionId, session.deliveryId, request.signal)) {
        if (event.kind === 'text') writer.write(formatDataStreamPart('text', event.delta));
        if (event.kind === 'tool') {
          if (actionOf[event.name]) writer.writeData({ action: actionOf[event.name] });
          writer.write(formatDataStreamPart('tool_call', { toolCallId: `${event.name}-${Date.now()}`, toolName: event.name, args: {} }));
        }
        if (event.kind === 'end' && event.outcome !== 'completed') writer.write(formatDataStreamPart('text', '\nThe agent stopped before it finished.'));
      }
    },
    onError: () => 'NEO agent stream failed',
  });
}
