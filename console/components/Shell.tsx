'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { motion } from 'motion/react';
import type { ReactNode } from 'react';
import { useRun } from './RunProvider';

const tabs = [['/', 'Overview'], ['/incident', 'Incident'], ['/radar', 'Radar'], ['/numbers', 'Numbers']] as const;
const sourceLabel = { engine: 'Live engine', recorded: 'Recorded engine run', fixture: 'Fixture run' } as const;

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const { source } = useRun();
  return (
    <div className="app">
      <header className="top">
        <div className="bar">
          <Link href="/" className="logo" aria-label="NEO">
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 2 22 20H2L12 2Z" fill="currentColor" /></svg>
            NEO
          </Link>
          <span className="slash" aria-hidden="true">/</span>
          <span className="crumb"><span className="avatar" aria-hidden="true" />demo-target</span>
          <div className="end">{source && <span className="where">{sourceLabel[source]} · EU</span>}</div>
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
      <main className="main">{children}</main>
    </div>
  );
}
