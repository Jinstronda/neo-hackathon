import type { Metadata, Viewport } from 'next';
import { GeistSans } from 'geist/font/sans';
import { GeistMono } from 'geist/font/mono';
import { RunProvider } from '@/components/RunProvider';
import { loadRun } from '@/lib/engine';
import { Shell } from '@/components/Shell';
import './globals.css';

export const metadata: Metadata = { title: 'NEO', description: 'Nothing reaches your cloud without proof.' };
export const viewport: Viewport = { themeColor: '#0a0a0a', colorScheme: 'dark' };

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const initial = await loadRun().catch(() => null);
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body><RunProvider initial={initial}><Shell>{children}</Shell></RunProvider></body>
    </html>
  );
}
