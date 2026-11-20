'use client';
import { useRun } from '@/components/RunProvider';
import { Terminal } from '@/components/Terminal';
import AttackGraph from '@/components/AttackGraph';
import InfraMap from '@/components/InfraMap';
import LiveTicker from '@/components/LiveTicker';
import { Record } from './Record';

export function Body() {
  const { run } = useRun();
  const events = run?.events ?? [];
  return (
    <div className="demo-body">
      <style>{css}</style>
      <LiveTicker events={events} />
      {run && <AttackGraph run={run.run} events={events} />}
      <div className="demo-grid">
        <section className="demo-col"><Terminal /></section>
        <section className="demo-col">{run && <InfraMap run={run.run} events={events} />}</section>
      </div>
      <Record />
    </div>
  );
}

const css = `
.demo-body { display: flex; flex-direction: column; gap: 14px; }
.demo-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr); gap: 14px; min-height: 420px; }
.demo-col { display: flex; flex-direction: column; gap: 14px; min-height: 0; }
.demo-col:first-child { height: 420px; }
@media (max-width: 1000px) { .demo-grid { grid-template-columns: 1fr; } }
`;
