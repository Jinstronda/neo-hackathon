'use client';
import { useMemo } from 'react';
import { useRun } from '@/components/RunProvider';
import { view } from '@/lib/state';
import { num } from '@/lib/types';

// production archive totals, no client named (ledger F-173)
const archive = [['41', 'organizations assessed'], ['44', 'assessments run'], ['106', 'findings'], ['491', 'evidence records']] as const;

export function Record() {
  const { run } = useRun();
  const full = useMemo(() => run ? view(run.run, run.events) : null, [run]);
  const m = full?.metrics;
  const tests = full?.tests;
  const thisRun = [
    [m?.minutes_exploit_to_fix != null ? `${m.minutes_exploit_to_fix}` : '--', 'minutes, exploit to fix'],
    [m?.cost_usd != null ? `$${m.cost_usd.toFixed(2)}` : '--', 'model cost'],
    [tests ? `${num(tests.passed)}/${num(tests.total)}` : '--', 'tests passing'],
    [m?.where || '--', 'where it ran'],
  ] as const;
  return (
    <div className="rec">
      <style>{css}</style>
      <Group title="This run" items={thisRun} />
      <Group title="NEO track record" items={archive} />
    </div>
  );
}

function Group({ title, items }: { title: string; items: readonly (readonly [string, string])[] }) {
  return (
    <section className="rec-g" aria-label={title}>
      <h2>{title}</h2>
      <dl>{items.map(([value, label]) => <div key={label}><dt>{value}</dt><dd>{label}</dd></div>)}</dl>
    </section>
  );
}

const css = `
.rec { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.rec-g { border: 1px solid var(--line); border-radius: var(--r-12); background: var(--bg-2); padding: 14px 16px; }
.rec-g h2 { font-size: var(--t-13); font-weight: 500; color: var(--muted); margin-bottom: 10px; }
.rec-g dl { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.rec-g dt { font-size: var(--t-24); font-weight: 600; letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
.rec-g dd { margin: 0; font-size: var(--t-12); color: var(--muted); }
@media (max-width: 900px) { .rec { grid-template-columns: 1fr; } .rec-g dl { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
`;
