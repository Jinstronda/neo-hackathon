import { num, text, type Agent, type Metrics, type RunEvent, type RunSummary } from './types';

// Everything the screens show, derived from the events seen so far. Nothing here is invented:
// a step with no event stays pending, an agent with no event stays idle.
export type TimelineRow = { key: string; label: string; at: number | null; detail: string; tone: 'red' | 'green' | 'plain' };
export type Finding = { id: string; model: string; cls: string; location: string; request: string; response: string; confirmedBy: string; at: number };
export type View = {
  agents: (Agent & { activity: string; busy: boolean })[];
  timeline: TimelineRow[];
  findings: Finding[];
  pre?: RunEvent; post?: RunEvent; patch?: RunEvent; reviews: RunEvent[]; tests?: RunEvent; merge?: RunEvent; mergeReady?: RunEvent; started?: RunEvent;
  proof: { scenario: string; before: boolean; after?: RunEvent }[];
  radar: RunEvent[]; twins: RunEvent[]; metrics: Partial<Metrics>; done: boolean;
};

const find = (events: RunEvent[], type: string, extra?: (event: RunEvent) => boolean) =>
  events.find((event) => event.type === type && (!extra || extra(event)));

export function view(run: RunSummary, events: RunEvent[]): View {
  const findings: Finding[] = events.filter((e) => e.type === 'red_finding').map((e) => ({
    id: text(e.finding_id), model: text(e.model), cls: text(e.cls), location: text(e.location),
    request: text(e.request), response: text(e.response), confirmedBy: text(e.confirmed_by), at: e.ts,
  }));
  const pre = find(events, 'flag_check', (e) => e.phase === 'pre-patch');
  // the gate: the replay on the rebuilt twin (post-patch), never the pre-patch replay
  const postRetest = (e: RunEvent) => e.phase === 'post-patch' || (e.phase === undefined && e.status === 'green');
  const post = find(events, 'retest', (e) => postRetest(e) && e.scenario === pre?.scenario) || find(events, 'retest', postRetest) || find(events, 'flag_check', (e) => e.phase === 'post-patch');
  // one line per scenario: did the exploit land before the patch, and on the rebuilt twin
  const scenarios = [...new Set(events.filter((e) => e.type === 'flag_check' && e.phase === 'pre-patch').map((e) => text(e.scenario)))];
  const proof = scenarios.map((scenario) => ({
    scenario,
    before: objectiveReached(find(events, 'flag_check', (e) => e.phase === 'pre-patch' && e.scenario === scenario)),
    after: find(events, 'retest', (e) => postRetest(e) && (e.scenario === scenario || (e.scenario === undefined && scenarios.length === 1))),
  }));
  const patch = find(events, 'blue_patch');
  const reviews = events.filter((e) => e.type === 'review');
  const tests = find(events, 'tests');
  const merge = find(events, 'merge');
  const mergeReady = find(events, 'merge_ready');
  const started = find(events, 'red_start');
  const rebuilt = find(events, 'twin_deploy', (e) => e.phase !== 'pre-patch');
  const metricsEvent = [...events].reverse().find((e) => e.type === 'metrics');
  const postDead = post ? post.objective_complete === false || post.objective_complete === 'False' || post.status === 'green' : false;
  const preWorks = pre ? pre.objective_complete === true || pre.objective_complete === 'True' : false;
  const row = (key: string, label: string, event: RunEvent | undefined, detail: string, tone: TimelineRow['tone'] = 'plain'): TimelineRow =>
    ({ key, label, at: event ? event.ts : null, detail: event ? detail : '', tone: event ? tone : 'plain' });
  const first = events.find((e) => e.type === 'red_finding');
  const timeline = [
    row('landed', 'Exploit landed', first, findings[0] ? `${findings[0].cls} on ${findings[0].location}` : '', 'red'),
    row('diagnosed', 'Diagnosed', pre, pre ? `Server flag check: objective reached${findings[0]?.confirmedBy && !/flag check/.test(findings[0].confirmedBy) ? `, confirmed by ${findings[0].confirmedBy}` : ''}` : '', preWorks ? 'red' : 'plain'),
    row('proposed', 'Patch proposed', patch, patch ? `${patch.pr_number ? `PR #${text(patch.pr_number)} ` : ''}${text(patch.branch)}` : ''),
    row('rebuilt', 'Twin rebuilt', rebuilt, rebuilt ? `${text(rebuilt.twin_id)} from ${text(rebuilt.image)}` : ''),
    row('retest', 'Retest', post, post ? (postDead ? 'Same exploit, objective not reached' : 'Exploit still works') : '', post ? (postDead ? 'green' : 'red') : 'plain'),
    row('verified', 'Verified', tests && postDead ? tests : undefined, tests ? `${num(tests.passed)}/${num(tests.total)} tests, ${num(tests.regression_added)} regression added` : '', 'green'),
  ];
  const agents = run.agents.map((agent) => {
    let activity = 'Idle', busy = false;
    if (agent.role === 'red') {
      const own = [...events].reverse().find((e) => e.type === 'red_finding' && e.model === agent.label);
      const mine = events.filter((e) => e.type === 'red_finding' && (e.model === agent.label || (Array.isArray(e.found_by) && e.found_by.includes(agent.label))));
      if (mine.length > 1) activity = `Found ${mine.length}: ${mine.map((e) => text(e.cls)).join(', ')}`;
      else if (own) activity = `Found ${text(own.cls).toLowerCase()} at ${text(own.location)}`;
      else if (started) { activity = pre ? 'Swept, no new finding' : 'Attacking the twin'; busy = !pre; }
    } else if (agent.role === 'blue') {
      if (patch) activity = patch.pr_number ? `Opened PR #${text(patch.pr_number)}` : `Patched ${text(patch.branch)}`;
    } else {
      const own = reviews.find((r) => r.reviewer === agent.label);
      if (own) activity = own.verdict === 'approve' ? 'Approved after re-running the exploit' : 'Requested changes after re-running the exploit';
      else if (patch) { activity = 'Reviewing the diff'; busy = true; }
    }
    return { ...agent, activity, busy };
  });
  const metrics: Partial<Metrics> = metricsEvent ? {
    minutes_exploit_to_fix: num(metricsEvent.minutes_exploit_to_fix), cost_usd: num(metricsEvent.cost_usd), where: text(metricsEvent.where),
    tested_surface: num(metricsEvent.tested_surface), untested_surface: num(metricsEvent.untested_surface), regression_tests: num(metricsEvent.regression_tests),
    ...(metricsEvent.lockin_before !== undefined ? { lockin_before: num(metricsEvent.lockin_before), lockin_after: num(metricsEvent.lockin_after) } : {}),
  } : {};
  return {
    agents, timeline, findings, pre, post, patch, reviews, tests, merge, mergeReady, started, proof,
    radar: events.filter((e) => e.type === 'radar_match'), twins: events.filter((e) => e.type === 'twin_create' || (e.type === 'twin_deploy' && e.phase !== 'pre-patch')),
    metrics, done: Boolean(merge || metricsEvent),
  };
}

export const objectiveReached = (event?: RunEvent) => Boolean(event && (event.objective_complete === true || event.objective_complete === 'True'));
