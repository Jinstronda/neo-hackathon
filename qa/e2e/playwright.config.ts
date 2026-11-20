import { defineConfig } from '@playwright/test';

// Drives the live NEO console preview in a fresh browser context, exactly as a judge would,
// except it carries the Vercel protection-bypass header so automation can reach the SSO-gated
// preview. BASE_URL and NEO_BYPASS come from the environment; see qa/e2e/run.sh.
const bypass = process.env.NEO_BYPASS;

export default defineConfig({
  testDir: '.',
  timeout: 300_000,
  expect: { timeout: 20_000 },
  retries: 0,
  reporter: [['list'], ['html', { outputFolder: 'report', open: 'never' }]],
  use: {
    baseURL: process.env.BASE_URL,
    extraHTTPHeaders: bypass ? { 'x-vercel-protection-bypass': bypass } : {},
    trace: 'on',
    video: 'on',
    screenshot: 'on',
  },
});
