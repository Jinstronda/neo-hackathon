import { allowedEmail, clearCookie, passwordOk, sessionCookie } from '@/lib/session';

export async function POST(request: Request) {
  const form = await request.formData().catch(() => null);
  const email = String(form?.get('email') ?? '').trim(), password = String(form?.get('password') ?? '');
  if (!allowedEmail(email) || !passwordOk(password)) {
    // ponytail: fixed delay per failure; add a per-IP limiter (Vercel firewall rule) if the URL gets abused
    await new Promise((resolve) => setTimeout(resolve, 1000));
    return Response.redirect(new URL('/login?error=1', request.url), 303);
  }
  return new Response(null, { status: 303, headers: { location: '/', 'set-cookie': sessionCookie(email) } });
}

export async function DELETE() {
  return new Response(null, { status: 204, headers: { 'set-cookie': clearCookie } });
}
