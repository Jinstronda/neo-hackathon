'use client';
import { animate, motion, useMotionValue, useTransform } from 'motion/react';
import { useEffect } from 'react';
import { useRun } from './RunProvider';

function Count({ to, format }: { to: number; format: (v: number) => string }) {
  const value = useMotionValue(0);
  const shown = useTransform(value, format);
  useEffect(() => { const c = animate(value, to, { duration: 0.9, ease: [0.16, 1, 0.3, 1] }); return () => c.stop(); }, [to, value]);
  return <motion.strong>{shown}</motion.strong>;
}

export function Numbers() {
  const { view } = useRun();
  const m = view?.metrics;
  if (!view) return <div className="card" style={{ padding: 16 }}><div className="skel" /></div>;
  if (!m || m.minutes_exploit_to_fix === undefined) return <section className="card"><div className="empty"><strong>No finished run yet</strong>Numbers fill when the loop reaches verified</div></section>;
  const total = (m.tested_surface ?? 0) + (m.untested_surface ?? 0) || 1;
  const tested = Math.round(((m.tested_surface ?? 0) / total) * 100);
  return (
    <div className="stack">
      <section className="card stats" aria-label="Run numbers" style={{ gridTemplateColumns: `repeat(${m.cost_usd ? 4 : 3}, minmax(0, 1fr))` }}>
        <div className="stat"><span>Exploit to verified fix</span><Count to={m.minutes_exploit_to_fix} format={(v) => `${Math.round(v)} min`} /></div>
        {m.cost_usd ? <div className="stat"><span>Cost of the run</span><Count to={m.cost_usd} format={(v) => `$${v.toFixed(2)}`} /></div> : null}
        <div className="stat"><span>Regression tests</span><Count to={m.regression_tests ?? 0} format={(v) => `${Math.round(v)}`} /></div>
        <div className="stat"><span>Runs on</span><strong>{m.where}</strong></div>
      </section>
      {total > 1 && <section className="card surface" aria-label="Surface">
        <div className="agent-h"><b>Surface</b></div>
        <div className="meter" role="img" aria-label={`${tested}% tested`}>
          <motion.i style={{ width: `${tested}%`, background: 'var(--green)' }} initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }} />
          <motion.i style={{ width: `${100 - tested}%`, background: 'var(--line-3)' }} initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 0.8, delay: 0.2 }} />
        </div>
        <div className="legend"><span><b className="num">{m.tested_surface}</b>tested</span><span><b className="num">{m.untested_surface}</b>untested</span></div>
      </section>}
      {m.lockin_before !== undefined && (
        <section className="card lockin" aria-label="Lock-in">
          <span className="soft">Services under US law</span><strong className="num">{m.lockin_before} → {m.lockin_after}</strong>
        </section>
      )}
    </div>
  );
}
