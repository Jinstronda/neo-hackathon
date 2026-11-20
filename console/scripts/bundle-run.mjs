// Bundles the engine's recorded run (../runs/demo-run) into public/runs/demo-run.json for replay mode.
// Keeps the committed copy when the engine run is not reachable from the build.
import { existsSync, readFileSync, writeFileSync } from 'node:fs';

const dir = new URL('../../runs/demo-run/', import.meta.url);
if (existsSync(new URL('run.json', dir))) {
  const run = JSON.parse(readFileSync(new URL('run.json', dir), 'utf8'));
  const events = readFileSync(new URL('events.jsonl', dir), 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line));
  writeFileSync(new URL('../public/runs/demo-run.json', import.meta.url), JSON.stringify({ run, events }));
  console.log(`bundled demo-run: ${events.length} events`);
} else console.log('engine run not found, keeping committed demo-run.json');
