import type { Metadata } from 'next';

export const metadata: Metadata = { title: 'Sign in · NEO' };

export default async function Login({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const { error } = await searchParams;
  return (
    <div className="page login">
      <form className="card login-card" method="post" action="/api/login">
        <h1>Sign in</h1>
        <label>Email<input name="email" type="email" autoComplete="email" required placeholder="you@homodeus.co" /></label>
        <label>Password<input name="password" type="password" autoComplete="current-password" required /></label>
        {error && <p className="red">Email or password not accepted</p>}
        <button className="btn primary" type="submit">Sign in</button>
      </form>
    </div>
  );
}
