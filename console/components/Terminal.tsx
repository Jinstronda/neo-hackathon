'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useRun } from './RunProvider';
import { clock, num, prTag, text, type RunEvent } from '@/lib/types';

type Tone = 'red' | 'green' | 'amber' | 'soft' | '';
type Line = { ts: number; who: string; msg: string; tone: Tone };

const STEP_MS = 360;
const yes = (v: unknown) => v === true || v === 'True';
// first evidence object of a finding, as key=value pairs: what the server saw
const evidence = (value: unknown) => {
  const first = Array.isArray(value) ? value[0] : null;
  if (!first || typeof first !== 'object') return '';
  return Object.entries(first as Record<string, unknown>).filter(([k]) => k !== 'type').map(([k, v]) => `${k}=${typeof v === 'string' && /\s|'/.test(v) ? JSON.stringify(v) : text(v)}`).join(' ');
};

// one narrated line per real event; unknown types are skipped, never invented
function narrate(e: RunEvent): Line | null {
  const at = (who: string, msg: string, tone: Tone = '') => ({ ts: e.ts, who, msg, tone });
  switch (e.type) {
    case 'radar_match': return at('radar', `${text(e.cve)} matched ${text(e.package)} ${text(e.version)}, KEV=${yes(e.kev)} EPSS=${num(e.epss).toFixed(2)}${yes(e.reachable) ? ', reachable' : ''}`, 'amber');
    case 'twin_create': case 'twin_deploy': return at('twin', `${text(e.twin_id)} up from ${text(e.image)}${e.phase ? ` (${text(e.phase)})` : ''}`, 'soft');
    case 'red_start': return at('red', `${(e.models as string[] | undefined)?.length ?? 0} open-weight models attacking ${text(e.twin_id)}`);
    case 'red_finding': return at(text(e.model), `${text(e.location)} -> ${text(e.cls)} ${evidence(e.response)} (CONFIRMED)`, 'red');
    case 'flag_check': return yes(e.objective_complete)
      ? at('flag', `${text(e.scenario)} ${text(e.phase)}: objective reached`, 'red')
      : at('flag', `${text(e.scenario)} ${text(e.phase)}: objective not reached`, 'green');
    case 'blue_patch': return at('blue', `opening ${prTag(e) || 'the patch'} on ${text(e.branch)}`);
    case 'review': return at('review', `${text(e.reviewer)} (${text(e.vendor)}): ${text(e.verdict)}`, e.verdict === 'approve' ? 'green' : 'amber');
    case 'review_disagreement': return at('review', `vendors disagree on ${prTag(e) || 'the patch'}, resolution: ${text(e.resolution)}`, 'amber');
    case 'exploit_run': return at('exploit', `${text(e.exploit)} exit ${text(e.exit)}  ${text(e.tail).trim().slice(0, 72)}`, num(e.exit) === 0 ? 'red' : 'green');
    case 'retest': return at('retest', `${text(e.scenario)} ${text(e.phase)}: ${text(e.status)}`, e.status === 'green' ? 'green' : 'red');
    case 'retest_summary': return at('retest', `${text(e.phase)} summary: ${text(e.status)}, gate ${yes(e.gate_pass) ? 'pass' : 'fail'}`, e.status === 'green' ? 'green' : 'red');
    case 'tests': return at('tests', `${num(e.passed)}/${num(e.total)} passed, ${num(e.regression_added)} regression tests added`, yes(e.ok) ? 'green' : 'red');
    case 'merge_ready': return at('merge', yes(e.ready) ? `${prTag(e) || 'patch'} ready to merge` : `held for a ${text(e.awaiting)}: ${(e.blockers as string[] | undefined)?.join('; ') ?? ''}`, 'amber');
    case 'merge': return at('merge', `${prTag(e) || 'patch'} merged by ${text(e.by)}`, 'green');
    case 'metrics': return at('metrics', `${num(e.minutes_exploit_to_fix)} min exploit to fix, $${num(e.cost_usd).toFixed(4)}, ${text(e.where)}`);
    default: return null;
  }
}

export function Terminal() {
  const { run } = useRun();
  const lines = useMemo(() => (run?.events ?? []).map(narrate).filter((l): l is Line => Boolean(l)), [run]);
  const [shown, setShown] = useState(0);
  const [round, setRound] = useState(0);
  const body = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!lines.length) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setShown(lines.length); return; }
    setShown(0);
    const timer = setInterval(() => setShown((n) => { if (n >= lines.length) { clearInterval(timer); return n; } return n + 1; }), STEP_MS);
    return () => clearInterval(timer);
  }, [lines, round]);
  useEffect(() => { body.current?.scrollTo({ top: body.current.scrollHeight }); }, [shown]);
  const playing = shown < lines.length;
  return (
    <section className="term" aria-label="NEO run log">
      <style>{css}</style>
      <div className="term-bar">
        <span className="term-title">neo · {run?.run.id ?? 'run'}</span>
        <button className="term-btn" onClick={() => setRound((r) => r + 1)} disabled={!lines.length}>{playing ? 'Restart' : 'Replay'}</button>
      </div>
      <div className="term-body" ref={body} role="log" aria-live="polite">
        <div className="term-line"><span className="soft">$</span> neo run --target demo-target --where eu{run?.source !== 'engine' ? ' --replay' : ''}</div>
        {!run && <div className="term-line soft">loading run…</div>}
        {lines.slice(0, shown).map((line, i) => (
          <div key={i} className="term-line">
            <span className="term-ts">[{clock(line.ts)}]</span> <span className="term-who">{line.who}:</span> <span className={line.tone}>{line.msg}</span>
          </div>
        ))}
        {run && <div className="term-line"><span className="soft">{playing ? '' : '$ '}</span><span className="term-caret" /></div>}
      </div>
    </section>
  );
}

const css = `
.term { display: flex; flex-direction: column; min-height: 0; height: 100%; background: #050505; border: 1px solid var(--line); border-radius: var(--r-12); overflow: hidden; }
.term-bar { display: flex; align-items: center; gap: 12px; height: 40px; padding: 0 12px; border-bottom: 1px solid var(--line); background: var(--surface); }
.term-title { flex: 1; color: var(--muted); font: 400 var(--t-12)/1 var(--mono); }
.term-btn { height: 26px; padding: 0 10px; border-radius: var(--r-6); border: 1px solid var(--line-2); background: var(--bg-2); color: var(--soft); font-size: var(--t-12); cursor: pointer; transition: color var(--fast), border-color var(--fast); }
.term-btn:hover { color: var(--fg); border-color: var(--line-3); }
.term-body { flex: 1; min-height: 0; overflow: auto; padding: 14px 16px; font: 400 13px/1.7 var(--mono); color: var(--fg); }
.term-line { white-space: pre-wrap; word-break: break-word; }
.term-ts { color: var(--muted); font-variant-numeric: tabular-nums; }
.term-who { color: var(--blue); }
.term-caret { display: inline-block; width: 8px; height: 15px; vertical-align: -3px; background: var(--fg); animation: term-blink 1s steps(1) infinite; }
@keyframes term-blink { 50% { opacity: 0; } }
@media (prefers-reduced-motion: reduce) { .term-caret { animation: none; } }
`;
