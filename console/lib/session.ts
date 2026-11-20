import 'server-only';
import { createHmac, timingSafeEqual } from 'node:crypto';
import { cookies } from 'next/headers';

// Team login: any @homodeus.com.br or @homodeus.co email plus the team password (NEO_TEAM_PASSWORD).
// The cookie holds the email and an HMAC over it; without a valid one the console runs in replay.
const COOKIE = 'neo_operator';
const key = () => process.env.NEO_TEAM_PASSWORD ?? '';
const sign = (email: string) => createHmac('sha256', key()).update(email).digest('base64url');

export const allowedEmail = (email: string) => /^[^@\s]+@homodeus\.(com\.br|co)$/i.test(email.trim());

export function passwordOk(password: string): boolean {
  const a = Buffer.from(password), b = Buffer.from(key());
  return key().length > 0 && a.length === b.length && timingSafeEqual(a, b);
}

export const sessionCookie = (email: string) =>
  `${COOKIE}=${encodeURIComponent(`${email.toLowerCase()}.${sign(email.toLowerCase())}`)}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=43200`;
export const clearCookie = `${COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0`;

export async function operator(): Promise<string | null> {
  if (!key()) return null;
  const raw = (await cookies()).get(COOKIE)?.value;
  if (!raw) return null;
  const at = raw.lastIndexOf('.');
  const email = raw.slice(0, at), mac = raw.slice(at + 1);
  const want = sign(email);
  return allowedEmail(email) && mac.length === want.length && timingSafeEqual(Buffer.from(mac), Buffer.from(want)) ? email : null;
}
