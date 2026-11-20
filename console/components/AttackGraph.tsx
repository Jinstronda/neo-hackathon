'use client';
import { useMemo } from 'react';
import { clock, num, prTag, text, type RunEvent, type RunSummary } from '@/lib/types';

// Kill chain as a node-link graph. Lit as far as the real events have progressed.
type Tone = 'red' | 'blue' | 'green' | 'amber' | 'fg';
type Node = { id: string; x: number; y: number; stage: string; title: string; sub: string; on: boolean; tone: Tone; value?: string; valueTone?: Tone };
type Edge = { from: string; to: string; tone: Tone };

const W = 1760, H = 470, NW = 128, NH = 46;
const COLS: [string, number][] = [['Intel', 80], ['Target', 250], ['Red team', 450], ['Bug class', 670], ['Proof', 870], ['Fixer', 1030], ['Patch', 1185], ['Review', 1345], ['Retest', 1505], ['Gate', 1670]];
const ROWS = [130, 250, 370];
const CLASSES = ['sql-injection', 'ssrf-metadata', 'weak-jwt-secret'];
const CLASS_OF: Record<string, string> = { 'sql-injection': 'sql-injection', ssrf: 'ssrf-metadata', 'ssrf-metadata': 'ssrf-metadata', 'weak-jwt-secret': 'weak-jwt-secret' };
const COLOR: Record<Tone, string> = { red: 'var(--red)', blue: 'var(--blue)', green: 'var(--green)', amber: 'var(--amber)', fg: 'var(--fg)' };
const MODELS = ['model-1', 'model-2', 'model-3'];

const first = (events: RunEvent[], test: (e: RunEvent) => boolean) => events.find(test);
const scenario = (e: RunEvent) => CLASS_OF[text(e.scenario) || text(e.cls)] ?? '';
const short = (s: string, n = 18) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

function derive(run: RunSummary, events: RunEvent[]) {
  const radar = first(events, (e) => e.type === 'radar_match');
  const start = first(events, (e) => e.type === 'red_start');
  const models = start && Array.isArray(start.models) ? (start.models as unknown[]).map(text) : [];
  const pre = events.filter((e) => e.type === 'flag_check' && e.phase === 'pre-patch' && e.objective_complete === true);
  const proven = new Set(pre.map(scenario));
  const findings = events.filter((e) => e.type === 'red_finding');
  // run.json lists every model that reached a class; events name the first one
  const foundBy = ((run as unknown as { findings?: { scenario?: string; found_by?: string[] }[] }).findings ?? []);
  const hit = (model: string, cls: string) => findings.some((f) => text(f.model) === model && scenario(f) === cls)
    || (proven.has(cls) && foundBy.some((f) => CLASS_OF[text(f.scenario)] === cls && (f.found_by ?? []).includes(model)));
  const patch = first(events, (e) => e.type === 'blue_patch');
  const review = (who: string) => first(events, (e) => e.type === 'review' && e.reviewer === who);
  const deploy = first(events, (e) => e.type === 'twin_deploy' && e.phase === 'post-patch');
  const post = events.filter((e) => e.type === 'retest' && e.phase === 'post-patch');
  const tests = first(events, (e) => e.type === 'tests');
  const ready = first(events, (e) => e.type === 'merge_ready');
  const merge = first(events, (e) => e.type === 'merge');
  return { radar, start, models, proven, findings, hit, patch, review, deploy, post, tests, ready, merge };
}

function graph(run: RunSummary, events: RunEvent[]) {
  const d = derive(run, events);
  const col = (i: number) => COLS[i][1];
  const verdict = (e?: RunEvent) => text(e?.verdict).replace('_', ' ');
  const vTone = (e?: RunEvent): Tone => (e?.verdict === 'approve' ? 'green' : 'amber');
  const live = d.post.filter((e) => e.status !== 'green').length;
  const nodes: Node[] = [
    { id: 'kev', x: col(0), y: ROWS[1], stage: 'Intel', title: text(d.radar?.cve) || 'KEV / CVE', sub: d.radar ? `${text(d.radar.package)} ${text(d.radar.version)}` : 'awaiting match', on: !!d.radar, tone: 'red', value: d.radar ? `EPSS ${(num(d.radar.epss) * 100).toFixed(1)}%${d.radar.kev === true ? ' · KEV' : ''}` : undefined },
    { id: 'target', x: col(1), y: ROWS[1], stage: 'Target', title: 'demo-target', sub: d.start ? text(d.start.twin_id) : 'twin not built', on: !!d.start, tone: 'red' },
    ...MODELS.map((m, i): Node => {
      const n = CLASSES.filter((c) => d.hit(m, c)).length;
      return { id: m, x: col(2), y: ROWS[i], stage: 'Red team', title: m, sub: d.models.includes(m) ? 'attacking twin' : 'idle', on: d.models.includes(m), tone: 'red', value: d.models.includes(m) ? `${n}/3 classes` : undefined };
    }),
    ...CLASSES.map((c, i): Node => {
      const f = d.findings.find((e) => scenario(e) === c);
      return { id: c, x: col(3), y: ROWS[i], stage: 'Bug class', title: c, sub: f ? short(text(f.location), 22) : 'unproven', on: d.proven.has(c), tone: 'red', value: d.proven.has(c) ? 'flag read' : undefined, valueTone: 'red' };
    }),
    { id: 'proof', x: col(4), y: ROWS[1], stage: 'Proof', title: 'confirmed', sub: 'server-side flag', on: d.proven.size > 0, tone: 'red', value: `${d.proven.size}/3 proven`, valueTone: 'red' },
    { id: 'blue', x: col(5), y: ROWS[1], stage: 'Fixer', title: 'fixer', sub: d.patch ? text(d.patch.branch) : 'waiting on proof', on: !!d.patch, tone: 'blue' },
    { id: 'pr', x: col(6), y: ROWS[1], stage: 'Patch', title: d.patch ? prTag(d.patch) || 'Patch' : 'PR', sub: d.patch ? `fixes ${text(d.patch.finding_id)}` : 'not opened', on: !!d.patch, tone: 'blue' },
    { id: 'security', x: col(7), y: 190, stage: 'Review', title: 'security', sub: d.review('security') ? 'reviewer 1' : 'pending', on: !!d.review('security'), tone: 'blue', value: verdict(d.review('security')) || undefined, valueTone: vTone(d.review('security')) },
    { id: 'correctness', x: col(7), y: 310, stage: 'Review', title: 'correctness', sub: d.review('correctness') ? 'reviewer 2' : 'pending', on: !!d.review('correctness'), tone: 'blue', value: verdict(d.review('correctness')) || undefined, valueTone: vTone(d.review('correctness')) },
    { id: 'retest', x: col(8), y: ROWS[1], stage: 'Retest', title: 'twin rebuilt', sub: d.tests ? `${num(d.tests.passed)}/${num(d.tests.total)} tests pass` : d.deploy ? text(d.deploy.twin_id) : 'not rebuilt', on: !!d.deploy, tone: 'green', value: d.post.length ? `${live}/${d.post.length} exploits live` : undefined, valueTone: live ? 'red' : 'green' },
    { id: 'gate', x: col(9), y: ROWS[1], stage: 'Gate', title: 'merge gate', sub: d.merge ? 'merged' : d.ready ? (d.ready.ready ? 'ready to merge' : 'held for human') : 'closed', on: !!(d.ready || d.merge), tone: d.merge ? 'green' : 'amber', value: d.ready && !d.merge && Array.isArray(d.ready.blockers) ? `${(d.ready.blockers as unknown[]).length} blocker` : undefined, valueTone: 'amber' },
  ];
  const edges: Edge[] = [
    { from: 'kev', to: 'target', tone: 'red' },
    ...MODELS.map((m): Edge => ({ from: 'target', to: m, tone: 'red' })),
    ...MODELS.flatMap((m) => CLASSES.map((c): Edge => ({ from: m, to: c, tone: 'red' }))),
    ...CLASSES.map((c): Edge => ({ from: c, to: 'proof', tone: 'red' })),
    { from: 'proof', to: 'blue', tone: 'blue' }, { from: 'blue', to: 'pr', tone: 'blue' },
    { from: 'pr', to: 'security', tone: 'blue' }, { from: 'pr', to: 'correctness', tone: 'blue' },
    { from: 'security', to: 'retest', tone: 'green' }, { from: 'correctness', to: 'retest', tone: 'green' },
    { from: 'retest', to: 'gate', tone: d.merge ? 'green' : 'amber' },
  ];
  const lit = (e: Edge) => (CLASSES.includes(e.to) ? d.hit(e.from, e.to) : nodes.find((n) => n.id === e.to)!.on);
  return { nodes, edges, lit, d };
}

const path = (a: Node, b: Node) => {
  const x1 = a.x + NW / 2, x2 = b.x - NW / 2, mx = (x1 + x2) / 2;
  return `M${x1},${a.y} C${mx},${a.y} ${mx},${b.y} ${x2},${b.y}`;
};

const CSS = `
.ag-flow { stroke-dasharray: 3 7; animation: ag-dash 1.1s linear infinite; }
.ag-node { transition: opacity var(--slow) var(--ease); }
@keyframes ag-dash { to { stroke-dashoffset: -20; } }
@media (prefers-reduced-motion: reduce) { .ag-flow { animation: none; } .ag-run { display: none; } }
`;

export default function AttackGraph({ run, events }: { run: RunSummary; events: RunEvent[] }) {
  const { nodes, edges, lit, d } = useMemo(() => graph(run, events), [run, events]);
  const by = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const stageTs = (types: string[]) => events.find((e) => types.includes(e.type))?.ts;
  const t0 = events[0]?.ts, tN = events[events.length - 1]?.ts;
  const elapsed = t0 && tN ? Math.round(tN - t0) : 0;
  const stamps: [number, number | undefined][] = [
    [0, stageTs(['radar_match'])], [1, stageTs(['red_start'])], [3, d.findings[0]?.ts], [5, stageTs(['blue_patch'])],
    [7, stageTs(['review'])], [8, d.deploy?.ts], [9, (d.merge ?? d.ready)?.ts],
  ];
  return (
    <section className="card" aria-label="Kill chain graph">
      <style>{CSS}</style>
      <div className="card-h">
        <span>Kill chain</span>
        <span className="mono muted">{run.id}</span>
        <span className="end mono num">
          T+{String(Math.floor(elapsed / 60)).padStart(2, '0')}:{String(elapsed % 60).padStart(2, '0')}
          <span className="muted"> · {events.length} events · {d.proven.size}/3 proven · {run.where}</span>
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block', maxHeight: '62dvh', background: 'var(--bg-2)' }} role="img" aria-label={`Kill chain: ${nodes.filter((n) => n.on).length} of ${nodes.length} nodes reached`}>
        <defs>
          <pattern id="ag-grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="rgba(255,255,255,.035)" strokeWidth="1" /></pattern>
          <filter id="ag-glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3.5" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
        </defs>
        <rect width={W} height={H} fill="url(#ag-grid)" />
        {COLS.map(([label, x]) => (
          <g key={label}>
            <line x1={x} x2={x} y1={56} y2={H - 44} stroke="var(--line)" strokeDasharray="2 6" />
            <text x={x} y={38} textAnchor="middle" fill="var(--muted)" style={{ font: '500 11px var(--mono)', letterSpacing: '.12em', textTransform: 'uppercase' }}>{label}</text>
          </g>
        ))}
        {stamps.map(([i, ts]) => ts ? <text key={i} x={COLS[i][1]} y={H - 20} textAnchor="middle" fill="var(--muted)" style={{ font: '400 11px var(--mono)' }}>{clock(ts)}</text> : null)}
        {edges.map((e) => {
          const a = by[e.from], b = by[e.to], p = path(a, b), on = lit(e), frontier = !on && a.on;
          const c = COLOR[e.tone];
          return (
            <g key={`${e.from}-${e.to}`}>
              <path d={p} fill="none" stroke={on || frontier ? c : 'var(--line-2)'} strokeOpacity={on ? 0.75 : frontier ? 0.45 : 0.5} strokeWidth={on ? 1.4 : 1} className={frontier ? 'ag-flow' : undefined} filter={on ? 'url(#ag-glow)' : undefined} />
              {on && (
                <circle className="ag-run" r="2.2" fill={c} filter="url(#ag-glow)">
                  <animateMotion dur={`${2.4 + (p.length % 7) * 0.2}s`} repeatCount="indefinite" path={p} />
                </circle>
              )}
            </g>
          );
        })}
        {nodes.map((n) => {
          const c = COLOR[n.tone];
          return (
            <g key={n.id} className="ag-node" transform={`translate(${n.x - NW / 2},${n.y - NH / 2})`} opacity={n.on ? 1 : 0.42}>
              {n.on && <rect width={NW} height={NH} rx="5" fill="none" stroke={c} strokeOpacity=".5" filter="url(#ag-glow)" />}
              <rect width={NW} height={NH} rx="5" fill={n.on ? 'var(--surface)' : 'var(--bg-2)'} stroke={n.on ? c : 'var(--line-2)'} strokeOpacity={n.on ? 0.9 : 1} strokeWidth={n.on ? 1.2 : 1} />
              <text x="10" y="19" fill={n.on ? 'var(--fg)' : 'var(--muted)'} style={{ font: '500 12px var(--mono)' }}>{short(n.title)}</text>
              <text x="10" y="35" fill="var(--muted)" style={{ font: '400 10.5px var(--mono)' }}>{short(n.sub, 21)}</text>
              {n.value && <text x={NW / 2} y={NH + 16} textAnchor="middle" fill={COLOR[n.valueTone ?? n.tone]} style={{ font: '500 10.5px var(--mono)', fontVariantNumeric: 'tabular-nums' }}>{n.value}</text>}
            </g>
          );
        })}
      </svg>
    </section>
  );
}
