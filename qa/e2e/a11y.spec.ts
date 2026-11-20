import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

for (const path of ['/', '/incident', '/radar', '/numbers']) {
  test(`axe: no serious or critical on ${path}`, async ({ page }) => {
    await page.goto(path);
    await page.waitForLoadState('networkidle').catch(() => {});
    const results = await new AxeBuilder({ page }).analyze();
    const bad = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
    // eslint-disable-next-line no-console
    console.log(`axe ${path}: ${bad.length} serious/critical, ${results.violations.length} total -> ${bad.map((v) => v.id).join(', ') || 'clean'}`);
    expect(bad, bad.map((v) => `${v.id}: ${v.nodes.length}`).join('; ')).toHaveLength(0);
  });
}
