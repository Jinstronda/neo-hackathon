import { test, expect } from '@playwright/test';

// Break the seam on purpose, before the judges do. Each fault must end in an honest degraded
// state: a message, an empty state, a re-enabled control. None may hang on a spinner forever or
// leave a blank screen. Faults are injected at the browser with route interception, so these are
// deterministic and need no change to the deployed env.

test('engine /api/run fails: the console degrades, it does not crash', async ({ page }) => {
  await page.route('**/api/run', (route) => route.abort('failed'));
  await page.goto('/');
  // the shell and chat still render; RunProvider catches the failure and shows skeletons/empty
  await expect(page.getByLabel('Chat with NEO')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Numbers' })).toBeVisible();
  await page.screenshot({ path: 'screens/fault-run-down.png', fullPage: true });
});

test('Eve agent down: chat shows an error and the composer re-enables, no endless spinner', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByLabel('Chat with NEO')).toBeVisible();
  await page.route('**/api/chat', (route) =>
    route.fulfill({ status: 502, contentType: 'application/json', body: JSON.stringify({ error: 'NEO agent unreachable' }) }));
  const attack = page.getByRole('button', { name: 'Attack our demo app' });
  await attack.click();
  // after the 502 the loop must not hang: the suggestion buttons (gated only by busy) end enabled,
  // so the operator can retry. A stuck "Thinking" with the buttons disabled forever is the failure.
  await expect(attack).toBeEnabled({ timeout: 15_000 });
  await expect(page.getByText('Thinking')).toHaveCount(0);
  await page.screenshot({ path: 'screens/fault-eve-down.png', fullPage: true });
});

test('double click on attack does not fire the loop twice', async ({ page }) => {
  let attacks = 0;
  await page.route('**/api/chat', async (route) => {
    attacks += 1;
    await new Promise((r) => setTimeout(r, 400));
    await route.fulfill({ status: 200, contentType: 'text/plain; charset=utf-8', body: '0:"one attack"\n' });
  });
  await page.goto('/');
  const button = page.getByRole('button', { name: 'Attack our demo app' });
  await button.click();
  await button.click({ force: true }).catch(() => {});
  await page.waitForTimeout(1500);
  expect(attacks, 'the composer disables while busy, so a second click is a no-op').toBe(1);
  await page.screenshot({ path: 'screens/fault-double-click.png', fullPage: true });
});

test('slow engine stream: the UI shows progress, it does not freeze', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByLabel('Chat with NEO')).toBeVisible();
  await page.route('**/api/stream**', async (route) => {
    await new Promise((r) => setTimeout(r, 8_000)); // a 30s model call would feel like this
    await route.continue();
  });
  await page.getByRole('button', { name: 'Attack our demo app' }).click();
  // the agent still answers through /api/chat; the screen is responsive, the tab is still there
  await expect(page.getByRole('link', { name: 'Numbers' })).toBeVisible();
  await page.screenshot({ path: 'screens/fault-slow-stream.png', fullPage: true });
});
