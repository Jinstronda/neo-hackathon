import { engineAction, loadRun } from '@/lib/engine';
import { operator } from '@/lib/session';

export const dynamic = 'force-dynamic';

export async function GET() {
  return Response.json(await loadRun(Boolean(await operator())), { headers: { 'cache-control': 'no-store' } });
}

export async function POST(request: Request) {
  if (!(await operator())) return Response.json({ error: 'sign in to drive the live engine' }, { status: 401 });
  const { action } = await request.json().catch(() => ({}));
  if (!['attack', 'fix', 'approve'].includes(action)) return Response.json({ error: 'action must be attack, fix or approve' }, { status: 400 });
  return Response.json(await engineAction(action));
}
