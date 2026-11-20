import 'server-only';
import { prTag, text, type RunEvent } from './types';

// Replay chat: NEO's lines for the recorded run, built only from that run's events.
type Turn = { tool: string; action?: string; reply: string };
const all = (events: RunEvent[], type: string) => events.filter((e) => e.type === type);

export function replayTurn(message: string, events: RunEvent[]): Turn {
  const m = message.toLowerCase();
  const findings = all(events, 'red_finding');
  const start = all(events, 'red_start')[0];
  if (/attack|hack|start|red team/.test(m)) {
    const models = Array.isArray(start?.models) ? start.models.length : 0;
    return { tool: 'attack_demo_app', action: 'attack', reply: `Starting. ${models} models attack twin ${text(start?.twin_id)}.` };
  }
  if (/find|found|what/.test(m)) {
    const first = findings[0];
    const pre = all(events, 'flag_check').filter((e) => e.phase === 'pre-patch' && (e.objective_complete === true || e.objective_complete === 'True'));
    return { tool: 'read_findings', reply: first
      ? `${findings.length} findings, each proven by the server-side flag check. First: ${text(first.cls)} at ${text(first.location)}. ${new Set(pre.map((e) => e.scenario)).size} exploits land on the twin.`
      : 'No findings in this run.' };
  }
  if (/fix|patch|repair/.test(m)) {
    const patch = all(events, 'blue_patch')[0];
    const green = all(events, 'retest').filter((e) => e.phase === 'post-patch' && e.status === 'green');
    const tests = all(events, 'tests')[0];
    return { tool: 'fix_finding', action: 'fix', reply: patch
      ? `${prTag(patch) ? `Patch ${prTag(patch)} is open.` : 'The patch is up.'} Replayed on the rebuilt twin, ${green.length} of ${green.length} exploits fail. Tests ${text(tests?.passed)}/${text(tests?.total)}. Waiting for your approval.`
      : 'No patch in this run.' };
  }
  if (/approv|merge|ship/.test(m)) {
    const merge = all(events, 'merge')[0], ready = all(events, 'merge_ready')[0];
    const blockers = Array.isArray(ready?.blockers) ? ready.blockers.join('; ') : '';
    return { tool: 'approve_merge', action: 'approve', reply: merge ? 'Merged.' : `Merge waits for a human: ${blockers || 'not ready'}.` };
  }
  return { tool: 'run_status', reply: 'This is a replay of the last real run. Say attack, what did you find, fix it, or approved.' };
}
