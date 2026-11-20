import { engineAction, loadRun } from '@/lib/engine';

export const dynamic = 'force-dynamic';

export async function GET() {
  return Response.json(await loadRun(), { headers: { 'cache-control': 'no-store' } });
}

export async function POST(request: Request) {
  const { action } = await request.json().catch(() => ({}));
  if (!['attack', 'fix', 'approve'].includes(action)) return Response.json({ error: 'action must be attack, fix or approve' }, { status: 400 });
  return Response.json(await engineAction(action));
}
