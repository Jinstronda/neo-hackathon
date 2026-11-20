import type { Metrics, Run, RunEvent } from './types';

const OUR_GITHUB = 'https://github.com/Jinstronda/';
const MEASURED = ['cost_usd', 'tested_surface', 'untested_surface', 'regression_tests'];
const omit = <T extends object>(o: T, keys: string[]) => Object.fromEntries(Object.entries(o).filter(([k]) => !keys.includes(k))) as T;

// Drops what a run claims but cannot back, at the one door every screen and route reads through:
// a PR number whose URL is not a PR on our GitHub, and live cost/surface the run did not measure.
// Screens then take their no-PR and no-cost paths instead of showing an invented value.
export function honest(run: Run): Run {
  const patch = run.events.find((e) => e.type === 'blue_patch');
  const realPr = typeof patch?.pr_url === 'string' && patch.pr_url.startsWith(OUR_GITHUB);
  const measured = run.source !== 'engine' || run.events.some((e) => e.type === 'metrics' && e.measured === true);
  const events = run.events.map((e): RunEvent => {
    let out = realPr ? e : omit(e, ['pr_number', 'pr_url']);
    if (!measured && e.type === 'metrics') out = omit(out, MEASURED);
    return out;
  });
  return { ...run, events, run: { ...run.run, metrics: measured ? run.run.metrics : omit(run.run.metrics ?? ({} as Metrics), MEASURED) } };
}
