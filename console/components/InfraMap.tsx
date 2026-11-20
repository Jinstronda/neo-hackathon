'use client';
import { clock, num, text, type Metrics, type RunEvent, type RunSummary } from '@/lib/types';

// Stylized topology of where a NEO run executes. Roles and regions only, never hosts or addresses.
// Every highlight, count and tick comes from the run's own events.
type NodeId = 'twin' | 'gateway' | 'github' | 'console';
type Tone = 'red' | 'green' | 'blue' | 'fg';

const NODES: Record<NodeId, { x: number; y: number; tag: string; name: string; region: string }> = {
  github: { x: 200, y: 150, tag: 'GIT', name: 'GitHub', region: 'PR + CI' },
  console: { x: 200, y: 320, tag: 'API', name: 'Console / API', region: 'Global edge, Vercel' },
  twin: { x: 640, y: 170, tag: 'TWN', name: 'Organizer server', region: 'EU, Leaseweb' },
  gateway: { x: 820, y: 300, tag: 'LLM', name: 'LLM gateway', region: 'EU' },
};
const ORDER: NodeId[] = ['twin', 'gateway', 'github', 'console'];

const TWIN = ['twin_create', 'red_start', 'red_finding', 'flag_check', 'exploit_run', 'twin_deploy', 'retest', 'retest_summary'];
const GIT = ['blue_patch', 'review', 'review_disagreement', 'tests', 'merge_ready', 'merge'];
// events produced by an agent reasoning through the gateway
const MODEL = ['red_start', 'red_finding', 'blue_patch', 'review', 'review_disagreement'];

const nodeOf = (e: RunEvent): NodeId => TWIN.includes(e.type) ? 'twin' : GIT.includes(e.type) ? 'github' : 'console';
const toneOf = (e?: RunEvent): Tone => !e ? 'fg' : e.phase === 'post-patch' || e.status === 'green' ? 'green' : nodeOf(e) === 'twin' ? 'red' : nodeOf(e) === 'github' ? 'blue' : 'fg';
const color = (t: Tone) => `var(--${t})`;

// edges follow the real data flow
// `ld` is the same curve drawn left to right so its label never renders upside down
const EDGES: { id: string; from: NodeId; to: NodeId; label: (pr: string) => string; d: string; ld?: string }[] = [
  { id: 'calls', from: 'twin', to: 'gateway', label: () => 'model calls', d: 'M640 170 C 720 170, 790 220, 820 300' },
  { id: 'pr', from: 'twin', to: 'github', label: (pr) => pr ? `PR #${pr}` : 'pull request', d: 'M640 170 C 480 90, 330 100, 200 150', ld: 'M200 150 C 330 100, 480 90, 640 170' },
  { id: 'record', from: 'github', to: 'console', label: () => 'recorded run', d: 'M176 168 C 96 210, 96 280, 176 302' },
];

// abstract EU silhouette and graticule, decorative only
const EU = 'M560 120 L600 92 L655 98 L690 82 L742 96 L770 132 L812 140 L860 176 L884 228 L872 286 L898 336 L862 384 L800 396 L742 372 L704 392 L652 366 L626 322 L584 314 L566 270 L540 238 L552 196 L532 160 Z';

function activeEdges(last: RunEvent | undefined, done: boolean): Set<string> {
  if (!last || done) return new Set();
  const s = new Set<string>();
  if (MODEL.includes(last.type)) s.add('calls');
  if (GIT.includes(last.type) || last.type === 'twin_deploy' || last.type === 'retest' || last.type === 'retest_summary') s.add('pr');
  if (last.type === 'tests' || last.type === 'merge_ready' || last.type === 'merge') s.add('record');
  return s;
}

export default function InfraMap({ run, events }: { run: RunSummary; events: RunEvent[] }) {
  const last = events[events.length - 1];
  const done = events.some((e) => e.type === 'metrics' || e.type === 'merge');
  const live = activeEdges(last, done);
  const activeNode: NodeId | null = !last || done ? null : nodeOf(last);
  const gatewayLive = live.has('calls');
  const tone = toneOf(last);
  const prEvent = events.find((e) => e.type === 'blue_patch');
  const pr = prEvent ? text(prEvent.pr_number) : '';
  const twinIds = [...new Set(events.filter((e) => e.twin_id).map((e) => text(e.twin_id)))];
  const counts = Object.fromEntries(ORDER.map((id) => [id, events.filter((e) => nodeOf(e) === id).length])) as Record<NodeId, number>;
  const lastAt = Object.fromEntries(ORDER.map((id) => [id, [...events].reverse().find((e) => nodeOf(e) === id)?.ts])) as Record<NodeId, number | undefined>;
  const m = run.metrics as Metrics & { cost_detail?: { calls?: number } };
  const calls = m.cost_detail?.calls;
  const findings = events.filter((e) => e.type === 'red_finding').length;
  const flags = events.filter((e) => e.type === 'flag_check').length;
  const t0 = events[0]?.ts ?? 0;
  const span = Math.max((last?.ts ?? t0) - t0, 1);
  const lanes: NodeId[] = ['twin', 'github', 'console'];

  const detail: Record<NodeId, string> = {
    twin: twinIds.length ? `${twinIds.length} disposable twin${twinIds.length > 1 ? 's' : ''}` : 'no twin yet',
    gateway: calls !== undefined ? `${calls} calls, run total` : 'model calls',
    github: pr ? `PR #${pr}, ${events.filter((e) => e.type === 'review').length} reviews` : 'waiting for a patch',
    console: done ? 'run recorded' : 'streaming events',
  };

  return (
    <section className="card" aria-label="Infrastructure map" style={{ background: '#07080a' }}>
      <div className="card-h">
        Infrastructure
        <span className="end mono" style={{ letterSpacing: '.04em' }}>NEO watches continuously · always on</span>
      </div>
      <svg viewBox="0 0 1000 520" role="img" aria-label="Run topology" style={{ display: 'block', width: '100%', height: 'auto' }}>
        <defs>
          <radialGradient id="im-glow"><stop offset="0%" stopColor={color(tone)} stopOpacity=".55" /><stop offset="100%" stopColor={color(tone)} stopOpacity="0" /></radialGradient>
          <pattern id="im-grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="#14171c" strokeWidth=".6" /></pattern>
        </defs>
        <rect width="1000" height="520" fill="url(#im-grid)" />
        {[100, 180, 260, 340].map((y) => <path key={y} d={`M0 ${y} Q500 ${y - 30} 1000 ${y}`} fill="none" stroke="#161a20" strokeWidth=".8" />)}
        {[260, 500, 740].map((x) => <path key={x} d={`M${x} 40 Q${x - 24} 220 ${x} 420`} fill="none" stroke="#161a20" strokeWidth=".8" />)}
        <path d={EU} fill="#0d1014" stroke="#232831" strokeWidth="1" />
        <text x="566" y="412" fill="var(--line-3)" fontFamily="var(--mono)" fontSize="10" letterSpacing="2">EU REGION · {text(run.where).toUpperCase()}</text>
        <text x="72" y="412" fill="var(--line-3)" fontFamily="var(--mono)" fontSize="10" letterSpacing="2">GLOBAL · SAAS + EDGE</text>

        {EDGES.map((edge) => {
          const on = live.has(edge.id);
          const recorded = done || (edge.id === 'calls' ? events.some((e) => MODEL.includes(e.type)) : edge.id === 'pr' ? Boolean(prEvent) : false);
          return (
            <g key={edge.id}>
              {edge.ld && <path id={`im-${edge.id}-l`} d={edge.ld} fill="none" />}
              <path id={`im-${edge.id}`} d={edge.d} fill="none" stroke={on ? color(tone) : recorded ? '#3a414c' : '#20252c'} strokeWidth={on ? 1.6 : 1} strokeDasharray={recorded || on ? undefined : '3 5'} />
              {on && (
                <path d={edge.d} fill="none" stroke={color(tone)} strokeWidth="2.6" strokeLinecap="round" strokeDasharray="18 600" opacity=".95">
                  <animate attributeName="stroke-dashoffset" from="618" to="0" dur="1.6s" repeatCount="indefinite" />
                </path>
              )}
              <text fill={on ? 'var(--fg)' : 'var(--muted)'} fontFamily="var(--mono)" fontSize="11" dy="-6">
                <textPath href={`#im-${edge.id}${edge.ld ? '-l' : ''}`} startOffset="50%" textAnchor="middle">{edge.label(pr)}</textPath>
              </text>
            </g>
          );
        })}

        {run.agents.map((agent, _i, all) => {
          const near: NodeId = agent.role === 'red' ? 'twin' : 'github';
          const group = all.filter((a) => (a.role === 'red') === (agent.role === 'red'));
          const k = group.indexOf(agent);
          const base = near === 'twin' ? -2.4 : 3.5;
          const a = base + k * 0.78;
          const n = NODES[near];
          const x = n.x + Math.cos(a) * 112, y = n.y + Math.sin(a) * 92;
          const acting = !done && last && (near === activeNode) && (agent.role === 'red' ? ['red_start', 'red_finding', 'flag_check'].includes(last.type) : GIT.includes(last.type));
          return (
            <g key={agent.id}>
              <line x1={n.x} y1={n.y} x2={x} y2={y} stroke={acting ? color(tone) : '#262b33'} strokeWidth={acting ? 1.2 : .7} />
              <rect x={x - 34} y={y - 10} width="68" height="20" rx="3" fill="#0b0d10" stroke={acting ? color(tone) : '#2a3039'} strokeWidth={acting ? 1.2 : .8} />
              <text x={x} y={y + 4} textAnchor="middle" fill={acting ? 'var(--fg)' : 'var(--soft)'} fontFamily="var(--mono)" fontSize="10">{agent.label}</text>
            </g>
          );
        })}

        {ORDER.map((id) => {
          const n = NODES[id];
          const on = id === activeNode || (id === 'gateway' && gatewayLive);
          return (
            <g key={id}>
              {on && <circle cx={n.x} cy={n.y} r="58" fill="url(#im-glow)" />}
              {on && (
                <circle cx={n.x} cy={n.y} r="30" fill="none" stroke={color(tone)} strokeWidth="1">
                  <animate attributeName="r" from="30" to="52" dur="1.8s" repeatCount="indefinite" />
                  <animate attributeName="opacity" from=".9" to="0" dur="1.8s" repeatCount="indefinite" />
                </circle>
              )}
              <circle cx={n.x} cy={n.y} r="34" fill="none" stroke={on ? color(tone) : '#2c323b'} strokeWidth=".8" strokeDasharray="2 4" />
              <circle cx={n.x} cy={n.y} r="24" fill={on ? '#12161c' : '#0b0d10'} stroke={on ? color(tone) : '#3a414c'} strokeWidth={on ? 2 : 1} />
              <text x={n.x} y={n.y + 4} textAnchor="middle" fill={on ? 'var(--fg)' : 'var(--soft)'} fontFamily="var(--mono)" fontSize="11" letterSpacing="1">{n.tag}</text>
              <text x={n.x} y={n.y + 52} textAnchor="middle" fill="var(--fg)" fontSize="12" fontWeight="500">{n.name}</text>
              <text x={n.x} y={n.y + 67} textAnchor="middle" fill="var(--muted)" fontFamily="var(--mono)" fontSize="10" letterSpacing="1">{n.region.toUpperCase()}</text>
            </g>
          );
        })}

        <g transform="translate(40 440)">
          {lanes.map((id, li) => (
            <g key={id} transform={`translate(0 ${li * 22})`}>
              <text x="0" y="4" fill="var(--muted)" fontFamily="var(--mono)" fontSize="9" letterSpacing="1.5">{NODES[id].tag}</text>
              <line x1="40" x2="920" y1="0" y2="0" stroke="#1b1f25" />
              {events.filter((e) => nodeOf(e) === id).map((e, i) => (
                <line key={`${e.ts}-${i}`} x1={40 + ((e.ts - t0) / span) * 880} x2={40 + ((e.ts - t0) / span) * 880} y1="-7" y2="7"
                  stroke={e === last && !done ? 'var(--fg)' : color(toneOf(e))} strokeWidth={e === last ? 2 : 1} opacity={e === last ? 1 : .7} />
              ))}
            </g>
          ))}
        </g>
      </svg>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', borderTop: '1px solid var(--line)' }}>
        {ORDER.map((id) => {
          const on = id === activeNode || (id === 'gateway' && gatewayLive);
          return (
            <div key={id} style={{ padding: '12px 16px', borderRight: '1px solid var(--line)', display: 'grid', gap: 2, background: on ? 'var(--hover)' : undefined }}>
              <span className="mono muted" style={{ letterSpacing: '.08em', fontSize: 10 }}>{NODES[id].tag} · {NODES[id].region.toUpperCase()}</span>
              <span style={{ fontWeight: on ? 600 : 500 }}>{NODES[id].name}</span>
              <span className="mono soft">{id === 'gateway' ? detail.gateway : `${counts[id]} events · ${detail[id]}`}</span>
              <span className="mono num muted">{lastAt[id] ? `last ${clock(lastAt[id]!)}` : id === 'gateway' ? 'traced per call' : 'no events yet'}</span>
            </div>
          );
        })}
      </div>

      <div className="mono num" style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 24px', padding: '12px 16px', borderTop: '1px solid var(--line)', color: 'var(--soft)' }}>
        <span><b style={{ color: 'var(--fg)' }}>{findings}</b> findings proven</span>
        <span><b style={{ color: 'var(--fg)' }}>{flags}</b> server flag checks</span>
        {done && <span><b style={{ color: 'var(--fg)' }}>{num(m.minutes_exploit_to_fix)}</b> min exploit to fix</span>}
        {done && <span><b style={{ color: 'var(--fg)' }}>${num(m.cost_usd).toFixed(4)}</b> run cost</span>}
        {done && <span><b style={{ color: 'var(--fg)' }}>{num(m.tested_surface)}/{num(m.tested_surface) + num(m.untested_surface)}</b> surface tested</span>}
        {done && <span><b style={{ color: 'var(--fg)' }}>{num(m.regression_tests)}</b> regression tests</span>}
        <span style={{ marginLeft: 'auto', color: 'var(--muted)' }}>All time: 41 orgs · 44 assessments · 106 findings · 491 evidence records</span>
      </div>
    </section>
  );
}
