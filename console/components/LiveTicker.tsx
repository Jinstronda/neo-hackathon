import { clock, num, prTag, text, type RunEvent } from '@/lib/types';

type Tone = 'red' | 'green' | 'amber' | '';
type Line = { ts: number | null; who: string; msg: string; tone: Tone };

const yes = (v: unknown) => v === true || v === 'True';
const tone: Record<Tone, string> = { red: 'var(--red)', green: 'var(--green)', amber: 'var(--amber)', '': 'var(--soft)' };
// design statement at the loop seam, not a record: carries no timestamp
const SEAM: Line[] = [
  { ts: null, who: 'neo', msg: 'NEO watches continuously. Every new exploit runs this same loop', tone: '' },
  { ts: null, who: 'loop', msg: 'radar -> red -> blue -> review -> retest -> human merge', tone: '' },
];

// one short line per real event; exploit output is never printed (it holds flags and tokens)
function narrate(e: RunEvent): Line | null {
  const at = (who: string, msg: string, t: Tone = ''): Line => ({ ts: e.ts, who, msg, tone: t });
  switch (e.type) {
    case 'radar_match': return at('radar', `${text(e.cve)} matched ${text(e.package)} ${text(e.version)}${yes(e.kev) ? ' (KEV)' : ''}, EPSS ${num(e.epss).toFixed(2)}${yes(e.reachable) ? ', reachable' : ''}`, 'amber');
    case 'red_start': return at('red', `${(e.models as unknown[] | undefined)?.length ?? 0} models attacking ${text(e.twin_id)}`);
    case 'red_finding': return at(text(e.model), `confirmed ${text(e.cls)} at ${text(e.location)}`, 'red');
    case 'flag_check': return at('flag', `${text(e.scenario)} ${text(e.phase)}: objective ${yes(e.objective_complete) ? 'reached' : 'not reached'}`, yes(e.objective_complete) ? 'red' : 'green');
    case 'blue_patch': return at('blue', `opened ${prTag(e) || 'the patch'} on ${text(e.branch)}`);
    case 'review': return at(text(e.reviewer), text(e.verdict).replace('_', ' '), e.verdict === 'approve' ? 'green' : 'amber');
    case 'review_disagreement': return at('review', `reviewers disagree on ${prTag(e) || 'the patch'}, routed to ${text(e.resolution)}`, 'amber');
    case 'twin_create': case 'twin_deploy': return at('twin', `${text(e.twin_id)} up from ${text(e.image)}${e.phase ? ` (${text(e.phase)})` : ''}`);
    case 'exploit_run': return at('exploit', `${text(e.exploit)} exit ${text(e.exit)}, ${num(e.exit) === 0 ? 'landed' : 'dead'}`, num(e.exit) === 0 ? 'red' : 'green');
    case 'retest': return at('retest', `${text(e.scenario)} ${text(e.phase)}: ${text(e.status)}`, e.status === 'green' ? 'green' : 'red');
    case 'retest_summary': return at('retest', `${text(e.phase)} gate ${yes(e.gate_pass) ? 'pass' : 'fail'}, ${text(e.status)}`, e.status === 'green' ? 'green' : 'red');
    case 'tests': return at('tests', `${num(e.passed)}/${num(e.total)} passed, ${num(e.regression_added)} regression added`, yes(e.ok) ? 'green' : 'red');
    case 'merge_ready': return at('merge', yes(e.ready) ? `${prTag(e) || 'patch'} ready` : `${prTag(e) || 'patch'} held for ${text(e.awaiting)}: ${(e.blockers as string[] | undefined)?.join('; ') ?? ''}`, 'amber');
    case 'merge': return at('merge', `${prTag(e) || 'patch'} merged by ${text(e.by)}`, 'green');
    case 'metrics': return at('metrics', `${num(e.minutes_exploit_to_fix)} min exploit to fix, $${num(e.cost_usd).toFixed(4)}, ${text(e.where)}, surface ${num(e.tested_surface)} tested / ${num(e.untested_surface)} untested`);
    default: return null;
  }
}

const CSS = `
.lt{position:relative;display:flex;align-items:stretch;height:28px;background:var(--bg-2);border-top:1px solid var(--line);border-bottom:1px solid var(--line);font-family:var(--mono);font-size:11px;line-height:28px;overflow:hidden;contain:paint}
.lt-tag{flex:none;padding:0 12px;border-right:1px solid var(--line);color:var(--muted);letter-spacing:.08em;font-variant-caps:all-small-caps;font-size:12px}
.lt-tag b{color:var(--fg);font-weight:500}
.lt-win{position:relative;flex:1;min-width:0;overflow:hidden;-webkit-mask-image:linear-gradient(90deg,transparent,#000 24px,#000 calc(100% - 48px),transparent);mask-image:linear-gradient(90deg,transparent,#000 24px,#000 calc(100% - 48px),transparent)}
.lt-track{display:flex;width:max-content;animation:lt-scroll var(--lt-dur) linear infinite;will-change:transform}
.lt:hover .lt-track{animation-play-state:paused}
.lt-seq{display:flex;flex:none}
.lt-i{flex:none;padding:0 18px;white-space:nowrap;border-right:1px solid var(--line)}
.lt-t{color:var(--muted);margin-right:8px;font-variant-numeric:tabular-nums}
.lt-w{color:var(--fg);margin-right:8px}
.lt-seam .lt-w,.lt-seam .lt-m{color:var(--muted)}
@keyframes lt-scroll{from{transform:translate3d(0,0,0)}to{transform:translate3d(-50%,0,0)}}
@media (prefers-reduced-motion:reduce){.lt-track{animation:none}.lt-win{overflow-x:auto}}
@media (max-width:640px){.lt-tag span{display:none}}
`;

export default function LiveTicker({ events }: { events: RunEvent[] }) {
  const lines = [...events].sort((a, b) => a.ts - b.ts).map(narrate).filter((l): l is Line => l !== null);
  if (!lines.length) return null;
  const seq = [...lines, ...SEAM];
  // ~70px/s reading speed, scaled to the text so a longer run does not scroll faster
  const dur = Math.max(30, Math.round(seq.reduce((n, l) => n + l.msg.length + l.who.length + 14, 0) * 6.6 / 70));
  const items = (copy: number) => (
    <div className="lt-seq" aria-hidden={copy > 0 || undefined}>
      {seq.map((l, i) => (
        <span key={i} className={l.ts == null ? 'lt-i lt-seam' : 'lt-i'}>
          {l.ts != null && <span className="lt-t">{clock(l.ts)}</span>}
          <span className="lt-w">{l.who}</span>
          <span className="lt-m" style={l.ts == null ? undefined : { color: tone[l.tone] }}>{l.msg}</span>
        </span>
      ))}
    </div>
  );
  return (
    <div className="lt" role="marquee" aria-label="NEO activity feed">
      <style>{CSS}</style>
      <div className="lt-tag"><b>NEO</b><span> feed · {lines.length} events</span></div>
      <div className="lt-win">
        <div className="lt-track" style={{ ['--lt-dur' as string]: `${dur}s` }}>{items(0)}{items(1)}</div>
      </div>
    </div>
  );
}
