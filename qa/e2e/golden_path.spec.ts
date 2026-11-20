import { test, expect, type APIRequestContext } from '@playwright/test';

// The stage script, as a test. It opens the public console, tells NEO to attack the demo app,
// and follows the Eve agent through the loop: a finding lands, the twin shows red, the PR and
// patch appear, the rebuilt twin shows green from the server-side flag check, and the numbers
// fill. Every assertion reads the expected value from /api/run, never from text the UI hardcodes,
// so a UI that fakes a step fails here.

interface RunEvent { type: string; phase?: string; [k: string]: unknown }
interface Served {
  source: string;
  run: { metrics: { minutes_exploit_to_fix: number } };
  events: RunEvent[];
}

async function served(request: APIRequestContext): Promise<Served> {
  const response = await request.get('/api/run');
  expect(response.ok(), 'GET /api/run must be reachable on the preview').toBeTruthy();
  return response.json();
}

const pick = (events: RunEvent[], type: string) => events.find((e) => e.type === type);

test('golden path: attack, find, red, fix, retest green, numbers', async ({ page, request }) => {
  const data = await served(request);
  const finding = pick(data.events, 'red_finding');
  const patch = pick(data.events, 'blue_patch');
  // the gate is the replay on the rebuilt twin; a real run also records the pre-patch replay (red)
  const retest = data.events.find((e) => e.type === 'retest' && e.phase === 'post-patch') ?? pick(data.events, 'retest');
  // the human merge gate: a merge, or merge_ready when a reviewer blocked it (the recorded run, PR #1)
  const merge = pick(data.events, 'merge') ?? pick(data.events, 'merge_ready');
  expect(finding, 'engine served a red_finding').toBeTruthy();
  expect(patch, 'engine served a blue_patch').toBeTruthy();
  expect(retest, 'engine served a retest').toBeTruthy();
  expect(merge, 'engine served the merge gate').toBeTruthy();
  const location = String(finding!.location);
  // pr_number is present only when a real PR was opened; the fixture/replay carries none
  const pr = patch!.pr_number != null ? String(patch!.pr_number) : null;
  // the retest gate: the exploit must be dead after the patch, decided server-side
  expect(retest!.objective_complete, 'retest objective_complete is false (exploit dead)').toBe(false);
  expect(retest!.status, 'retest is green').toBe('green');

  await page.goto('/');
  await expect(page.getByLabel('Chat with NEO')).toBeVisible();

  // 1. Attack: NEO runs the red team on a twin; the finding lands and the twin shows red.
  await page.getByRole('button', { name: 'Attack our demo app' }).click();
  await expect(page.getByText('Started the red team')).toBeVisible();
  await expect(page.getByText(location, { exact: false }).first()).toBeVisible({ timeout: 40_000 });
  await expect(page.getByText('red_finding').first()).toBeVisible();
  await page.screenshot({ path: `screens/1-attack-red.png`, fullPage: true });

  // 2. Fix: the blue agent patches; the rebuilt twin replays the exploit and it fails (green).
  // A real PR link appears only when the box opened one; the replay carries no PR, so assert the
  // retest beat (always present) and the PR text only when a pr_number was served.
  await page.getByRole('button', { name: 'Fix it' }).click();
  await expect(page.getByText('retest').first()).toBeVisible({ timeout: 40_000 });
  if (pr) await expect(page.getByText(`PR #${pr}`, { exact: false }).first()).toBeVisible();
  await page.screenshot({ path: `screens/2-fix-green.png`, fullPage: true });

  // The approve->merge beat depends on the live agent calling approve_merge, which gpt-6-luna does
  // not do reliably (ISSUES.md P0-4). It is covered separately in merge_beat.spec.ts, where the
  // merge seam is also proven deterministically. The find-fix-prove loop above is the reliable core.
  void pr;

  // 3. Numbers fill from the run. Navigate via the tab (client-side), as on stage: the streamed
  // metrics event stays in the run state. A hard reload would reset it, which is not the demo flow.
  await page.getByRole('link', { name: 'Numbers' }).click();
  await expect(page).toHaveURL(/\/numbers$/);
  await expect(page.getByText(`${Math.round(data.run.metrics.minutes_exploit_to_fix)} min`).first()).toBeVisible({ timeout: 20_000 });
  await page.screenshot({ path: `screens/4-numbers.png`, fullPage: true });

  // eslint-disable-next-line no-console -- test output
  console.log(`golden path done. source=${data.source} finding=${location} pr=${pr} retest=${retest!.status}`);
});
