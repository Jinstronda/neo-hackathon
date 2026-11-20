import { num, text, type RunEvent, type RunSummary } from './types';
import { objectiveReached, type View } from './state';

// The attack graph. Every node is an entity a real event produced, every edge a causal link
// between two of them. A node with no event does not exist yet; nothing here is invented.
export type Tone = 'red' | 'green' | 'amber' | 'plain';
export type GNode = { id: string; col: number; title: string; sub: string; tone: Tone; working: boolean; ts: number; facts: [string, string][]; href?: string };
export type GEdge = { from: string; to: string; tone: Tone; flowing: boolean };
export type Graph = { nodes: GNode[]; edges: GEdge[]; landed: number; dead: number };
export const LANES = ['Target', 'Attackers', 'Exploits', 'Fixer', 'Checks', 'Replay', 'Human'];

const yes = (v: unknown) => v === true || v === 'True';
// a finding's class (ssrf) and its scenario (ssrf-metadata) name the same exploit
const same = (scenario: unknown, cls: unknown) => {
  const s = text(scenario), c = text(cls);
  return Boolean(s && c && (s === c || s.startsWith(c) || c.startsWith(s)));
};
const facts = (pairs: [string, unknown][]): [string, string][] =>
  pairs.filter(([, v]) => v !== undefined && v !== null && v !== '' && !(Array.isArray(v) && !v.length))
    .map(([k, v]) => [k, Array.isArray(v) ? v.join(', ') : text(v)]);
const endpoint = (location: string) => location.split(' ').slice(0, 2).join(' ');
const foundBy = (e: RunEvent) => (Array.isArray(e.found_by) && e.found_by.length ? e.found_by.map(text) : [text(e.model)]);
// only a PR on our own GitHub is a link; anything else stays text
const realPr = (url: unknown) => (text(url).startsWith('https://github.com/Jinstronda/') ? text(url) : undefined);

export function graph(run: RunSummary, events: RunEvent[], v: View): Graph {
  const nodes: GNode[] = [];
  const edges: GEdge[] = [];
  const has = (id: string) => nodes.some((n) => n.id === id);
  const add = (n: Omit<GNode, 'working'> & { working?: boolean }) => { if (!has(n.id)) nodes.push({ working: false, ...n }); };
  const link = (from: string, to: string, tone: Tone = 'plain', flowing = false) => { if (has(from) && has(to)) edges.push({ from, to, tone, flowing }); };
  const live = (label: string) => v.agents.find((a) => a.label === label);
  const findings = events.filter((e) => e.type === 'red_finding');

  const radar = events.find((e) => e.type === 'radar_match');
  if (radar) add({
    id: 'cve', col: 0, title: text(radar.cve), sub: `${text(radar.package)} ${text(radar.version)}`, tone: yes(radar.kev) ? 'red' : 'plain', ts: radar.ts,
    facts: facts([['package', `${text(radar.package)} ${text(radar.version)}`], ['CISA KEV', yes(radar.kev) ? 'listed' : undefined],
      ['EPSS', radar.epss === undefined ? undefined : `${(num(radar.epss) * 100).toFixed(1)}%`],
      ['reachable', radar.reachable === undefined ? undefined : yes(radar.reachable) ? 'yes' : 'no'], ['advisories', radar.osv]]),
  });

  const start = v.started;
  const models = Array.isArray(start?.models) ? start.models.map(text) : [...new Set(findings.flatMap(foundBy))];
  if (start) {
    add({ id: 'twin', col: 0, title: text(start.twin_id), sub: 'pre-patch twin', tone: 'plain', ts: start.ts, facts: facts([['twin', start.twin_id], ['attacked by', models]]) });
    link('cve', 'twin');
  }
  for (const a of run.agents.filter((x) => x.role === 'red' && models.includes(x.label))) {
    const agent = live(a.label), working = agent?.status === 'working';
    add({ id: `a:${a.label}`, col: 1, title: a.label, sub: agent?.sub ?? '', tone: 'plain', working, ts: start?.ts ?? 0, facts: facts([['agent', a.label], ['runs on', agent?.sub], ['status', agent?.status]]) });
    link('twin', `a:${a.label}`, 'plain', working);
  }

  let landed = 0, dead = 0;
  for (const e of findings) {
    const id = `f:${text(e.finding_id)}`;
    const before = events.find((x) => x.type === 'flag_check' && x.phase === 'pre-patch' && same(x.scenario, e.cls));
    const after = events.find((x) => x.type === 'retest' && x.phase === 'post-patch' && same(x.scenario, e.cls));
    const hit = objectiveReached(before), killed = Boolean(after) && !objectiveReached(after);
    if (!has(id)) { landed += hit ? 1 : 0; dead += killed ? 1 : 0; }
    add({
      id, col: 2, title: text(e.cls), sub: endpoint(text(e.location)), tone: killed ? 'green' : hit ? 'red' : 'plain', ts: e.ts,
      facts: facts([['finding', e.finding_id], ['where', e.location], ['found by', foundBy(e)], ['confirmed by', e.confirmed_by],
        ['before patch', before ? (hit ? 'objective reached' : 'objective not reached') : undefined],
        ['after patch', after ? (killed ? 'objective not reached' : 'objective reached') : undefined]]),
    });
    foundBy(e).forEach((m) => link(`a:${m}`, id, hit && !killed ? 'red' : 'plain'));
  }

  const blue = run.agents.find((a) => a.role === 'blue');
  const fixer = blue ? live(blue.label) : undefined;
  const patch = v.patch;
  if (blue && fixer && fixer.status !== 'idle') {
    const working = fixer.status === 'working';
    add({
      id: 'fixer', col: 3, title: blue.label, sub: patch ? text(patch.branch) : 'writing the patch', tone: 'plain', working, ts: patch?.ts ?? v.pre?.ts ?? 0, href: realPr(patch?.pr_url),
      facts: facts([['branch', patch?.branch], ['PR', patch?.pr_number ? `#${text(patch.pr_number)}` : undefined], ['diff digest', text(patch?.digest).slice(0, 12)],
        ['commits', Array.isArray(patch?.commits) ? String(patch.commits.length) : undefined]]),
    });
    nodes.filter((n) => n.col === 2).forEach((n) => link(n.id, 'fixer', 'plain', working));
  }

  for (const a of run.agents.filter((x) => x.role === 'reviewer')) {
    const agent = live(a.label);
    if (!agent || agent.status === 'idle') continue;
    const own = v.reviews.find((r) => r.reviewer === a.label);
    const tone: Tone = !own ? 'plain' : own.verdict === 'approve' ? 'green' : 'amber';
    const checked = (own?.recheck_evidence as { verified?: string } | undefined)?.verified;
    add({
      id: `r:${a.label}`, col: 4, title: a.label, sub: own ? text(own.vendor) : agent.sub, tone, working: agent.status === 'working', ts: own?.ts ?? patch?.ts ?? 0,
      facts: facts([['vendor', own?.vendor], ['verdict', own ? (own.verdict === 'approve' ? 'approve' : 'request changes') : undefined], ['read', checked?.slice(0, 140)]]),
    });
    link('fixer', `r:${a.label}`, tone, agent.status === 'working');
  }

  const rebuilt = events.find((e) => e.type === 'twin_deploy' && e.phase === 'post-patch');
  if (rebuilt) {
    add({ id: 'rebuilt', col: 4, title: text(rebuilt.twin_id), sub: text(rebuilt.image), tone: 'plain', ts: rebuilt.ts, facts: facts([['twin', rebuilt.twin_id], ['image', rebuilt.image], ['phase', 'post-patch, rebuilt from the patch']]) });
    link('fixer', 'rebuilt');
  }

  for (const e of events.filter((x) => x.type === 'retest' && x.phase === 'post-patch')) {
    const killed = !objectiveReached(e), id = `p:${text(e.scenario)}`;
    add({ id, col: 5, title: text(e.scenario), sub: killed ? 'exploit failed' : 'exploit landed', tone: killed ? 'green' : 'red', ts: e.ts,
      facts: facts([['replayed on', rebuilt?.twin_id], ['objective_complete', yes(e.objective_complete) ? 'true' : 'false'], ['checked by', 'server-side flag check']]) });
    link('rebuilt', id, killed ? 'green' : 'red');
  }

  const gate = v.merge ?? v.mergeReady;
  if (gate) {
    const merged = Boolean(v.merge);
    add({
      id: 'human', col: 6, title: merged ? 'merged' : 'your approval', sub: merged ? `by ${text(v.merge?.by)}` : 'merge waits', tone: merged ? 'green' : 'amber', ts: gate.ts,
      facts: facts([['rule', v.mergeReady?.rule], ['approved by', v.mergeReady?.approved_by], ['blocking', v.mergeReady?.blockers]]),
    });
    // replays feed the gate; reviewer verdicts sit in its facts (an edge from them would cross the Replay lane)
    nodes.filter((n) => n.col === 5).forEach((n) => link(n.id, 'human', n.tone === 'green' ? 'green' : 'plain'));
  }
  return { nodes, edges, landed, dead };
}
