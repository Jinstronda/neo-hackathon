// node lib/honest.check.ts — a 404 PR and unmeasured live cost are dropped; a real PR, recorded and measured cost stay
import assert from 'node:assert/strict';
import { honest } from './honest.ts';
import type { Run } from './types.ts';

const run = (source: Run['source'], metrics: object, events: object[]) => ({ source, run: { metrics }, events }) as unknown as Run;
const fake = honest(run('engine', { cost_usd: 0.42, tested_surface: 83, minutes_exploit_to_fix: 3 }, [
  { type: 'blue_patch', pr_number: 81, pr_url: 'https://github.com/neo/demo-target/pull/81', branch: 'b' },
  { type: 'merge', pr_number: 81, by: 'human' },
  { type: 'metrics', cost_usd: 0.42, tested_surface: 83, minutes_exploit_to_fix: 3 }]));
assert.ok(!('pr_number' in fake.events[0]) && !('pr_url' in fake.events[0]) && !('pr_number' in fake.events[1]), 'a 404 PR survived');
assert.ok(!('cost_usd' in fake.events[2]) && !('tested_surface' in fake.run.metrics) && fake.events[2].minutes_exploit_to_fix === 3, 'unmeasured live cost survived');
const real = honest(run('recorded', { cost_usd: 0.09 }, [
  { type: 'blue_patch', pr_number: 1, pr_url: 'https://github.com/Jinstronda/neo-hackathon/pull/1' }, { type: 'metrics', cost_usd: 0.09 }]));
assert.equal(real.events[0].pr_number, 1);
assert.equal(real.events[1].cost_usd, 0.09);
assert.equal(honest(run('engine', {}, [{ type: 'metrics', cost_usd: 0.12, measured: true }])).events[0].cost_usd, 0.12);
console.log('honest: 3 cases pass');
