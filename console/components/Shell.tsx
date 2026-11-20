'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { motion } from 'motion/react';
import type { ReactNode } from 'react';
import { useRun } from './RunProvider';

const tabs = [['/', 'Overview'], ['/demo', 'Demo'], ['/incident', 'Incident'], ['/radar', 'Radar'], ['/numbers', 'Numbers']] as const;
const sha = process.env.NEXT_PUBLIC_COMMIT_SHA?.slice(0, 7);

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const { source, operator, playing } = useRun();
  return (
    <div className="app" data-playing={playing ?? undefined}>
      <header className="top">
        <div className="bar">
          <Link href="/" className="logo" aria-label="NEO">
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 2 22 20H2L12 2Z" fill="currentColor" /></svg>
            NEO
          </Link>
          <span className="slash" aria-hidden="true">/</span>
          <span className="crumb">demo-target</span>
          <div className="end">
            {source !== 'engine' && <span className="where">replay</span>}
            {operator ? <span className="where hide-sm">{operator}</span> : <Link className="btn" href="/login">Sign in</Link>}
          </div>
        </div>
        <nav className="tabs" aria-label="Sections">
          {tabs.map(([href, label]) => {
            const active = href === '/' ? path === '/' : path.startsWith(href);
            return (
              <Link key={href} href={href} className="tab" aria-current={active ? 'page' : undefined}>
                {label}
                {active && <motion.span layoutId="tab-line" className="tab-line" transition={{ type: 'spring', stiffness: 500, damping: 40 }} />}
              </Link>
            );
          })}
        </nav>
      </header>
      <main className="main" tabIndex={-1}>{children}{sha && <footer className="foot mono">{sha}</footer>}</main>
    </div>
  );
}
