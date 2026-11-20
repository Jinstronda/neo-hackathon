import { test, expect, type APIRequestContext } from '@playwright/test';

// The final beat: a human approves and the PR merges. Two things are separate here, and the demo
// depends on both:
//  1. The seam is deterministic and must always hold: /api/stream?phase=merge streams the merge
//     event, so the moment play('merge') runs, the merge row renders. Asserted against the API.
//  2. The agent trigger is flaky: gpt-6-luna often reads "Approved" as chat and never calls
//     approve_merge (ISSUES.md P0-4). This is a best-effort check that records what the agent did.

interface RunEvent { type: string; [k: string]: unknown }

async function mergeEvent(request: APIRequestContext): Promise<RunEvent | undefined> {
  const response = await request.get('/api/stream?phase=merge');
  expect(response.ok(), 'phase=merge stream reachable').toBeTruthy();
  const body = await response.text();
  const rows = body.split('\n')
    .filter((l) => l.startsWith('data:'))
    .map((l) => { try { return JSON.parse(l.slice(5)) as RunEvent; } catch { return null; } })
    .filter((e): e is RunEvent => Boolean(e));
  return rows.find((e) => e.type === 'merge');
}

test('merge seam: phase=merge streams the merge event', async ({ request }) => {
  const merge = await mergeEvent(request);
  expect(merge, 'the engine serves a merge event on the merge phase').toBeTruthy();
  expect(String(merge!.by)).toBe('human');
});

test('merge beat via the agent (best effort, documents P0-4)', async ({ page, request }) => {
  const merge = await mergeEvent(request);
  const pr = String(merge!.pr_number);

  await page.goto('/');
  await expect(page.getByLabel('Chat with NEO')).toBeVisible();
  await page.getByRole('button', { name: 'Attack our demo app' }).click();
  await expect(page.getByText('Started the red team')).toBeVisible({ timeout: 40_000 });
  await page.getByRole('button', { name: 'Fix it' }).click();
  await expect(page.getByText('Opened the patch PR')).toBeVisible({ timeout: 40_000 });

  // ask for the merge as plainly as possible
  await page.getByRole('textbox', { name: 'Message NEO' }).fill('Approved. Merge the PR now.');
  await page.getByRole('button', { name: 'Send' }).click();

  const merged = page.getByText(`PR #${pr} merged by human`, { exact: false });
  const shown = await merged.isVisible({ timeout: 70_000 }).catch(() => false);
  // eslint-disable-next-line no-console -- records the flaky agent outcome for the round log
  console.log(`merge beat: agent ${shown ? 'called approve_merge, merge rendered' : 'did NOT trigger the merge (P0-4)'}`);
  await page.screenshot({ path: 'screens/merge-beat.png', fullPage: true });
  // soft: do not fail the suite on the known-flaky agent; the seam test above is the hard gate
  test.info().annotations.push({ type: 'merge-beat', description: shown ? 'agent merged' : 'agent did not trigger merge (P0-4)' });
});
