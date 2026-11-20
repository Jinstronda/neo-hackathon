import type { Metadata, Viewport } from 'next';
import { GeistSans } from 'geist/font/sans';
import { GeistMono } from 'geist/font/mono';
import { RunProvider } from '@/components/RunProvider';
import { loadRun } from '@/lib/engine';
import { operator } from '@/lib/session';
import { Shell } from '@/components/Shell';
import { Presenter } from '@/components/Presenter';
import './globals.css';

export const metadata: Metadata = {
  metadataBase: new URL('https://neo-console-jinstrondas-projects.vercel.app'),
  title: { default: 'NEO', template: '%s · NEO' },
  description: 'Nothing reaches your cloud without proof.',
};
export const viewport: Viewport = { themeColor: '#0a0a0a', colorScheme: 'dark' };

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const who = await operator();
  const initial = await loadRun(Boolean(who)).catch(() => null);
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body><RunProvider initial={initial} operator={who}><Shell>{children}</Shell><Presenter /></RunProvider></body>
    </html>
  );
}
