'use client';
import { motion } from 'motion/react';
import { useEffect, useRef } from 'react';
import { useRun } from './RunProvider';
import { clock, text } from '@/lib/types';

const roleName = { red: 'Attack', blue: 'Patch', reviewer: 'Review' } as const;

export function Board() {
  const { view } = useRun();
  if (!view) return <div className="card"><div className="card-h">Agents</div><div style={{ padding: 16, display: 'grid', gap: 10 }}><div className="skel" /><div className="skel" style={{ width: '60%' }} /></div></div>;
  const busy = view.agents.filter((a) => a.busy).length;
  return (
    <section className="card" aria-label="Agents">
      <div className="card-h">Agents<span className="end">{busy ? `${busy} working` : `${view.agents.length} agents`}</span></div>
      <div className="agents">
        {view.agents.map((agent, index) => (
          <motion.div key={agent.id} className={`agent${agent.busy ? ' busy' : ''}`} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.04, duration: 0.3 }}>
            <div className="agent-h"><b>{agent.label}</b><span className="role">{roleName[agent.role]}</span></div>
            <motion.p key={agent.activity} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className={agent.busy ? 'shimmer-text' : undefined}>{agent.activity}</motion.p>
          </motion.div>
        ))}
      </div>
    </section>
  );
}

export function Timeline({ compact }: { compact?: boolean }) {
  const { view } = useRun();
  if (!view) return null;
  return (
    <section className="card" aria-label="Incident timeline">
      <div className="card-h">Incident timeline{view.findings[0] && <span className="end mono">{view.findings[0].id}</span>}</div>
      <div className="rows">
        {view.timeline.map((row) => (
          <motion.div layout key={row.key} className={`row${row.at ? '' : ' pending'}`}>
            <span className="at num">{row.at ? clock(row.at) : '--:--:--'}</span>
            <span className={`label ${row.tone === 'plain' ? '' : row.tone}`}>{row.label}</span>
            {!compact || row.at ? <span className="detail">{row.detail}</span> : <span />}
          </motion.div>
        ))}
      </div>
    </section>
  );
}

const describe = (e: Record<string, unknown>) => {
  switch (e.type) {
    case 'radar_match': return `${text(e.cve)} in ${text(e.package)} ${text(e.version)}`;
    case 'twin_create': case 'twin_deploy': return `${text(e.twin_id)} ${text(e.image)} on ${text(e.where)}`;
    case 'red_start': return `${(e.models as string[] | undefined)?.length ?? 0} models attacking ${text(e.twin_id)}`;
    case 'red_finding': return `${text(e.model)} ${text(e.cls)} ${text(e.location)}`;
    case 'flag_check': return `${text(e.phase)} objective_complete=${text(e.objective_complete)}`;
    case 'blue_patch': return `PR #${text(e.pr_number)} ${text(e.branch)}`;
    case 'review': return `${text(e.reviewer)} ${text(e.verdict)}`;
    case 'retest': return `objective_complete=${text(e.objective_complete)} ${text(e.status)}`;
    case 'tests': return `${text(e.passed)}/${text(e.total)} passed`;
    case 'metrics': return `${text(e.minutes_exploit_to_fix)} min, $${text(e.cost_usd)}`;
    case 'merge': return `PR #${text(e.pr_number)} merged by ${text(e.by)}`;
    case 'exploit_run': return `${text(e.exploit)} exit ${text(e.exit)}`;
    case 'retest_summary': return `${text(e.phase)} ${text(e.status)}`;
    case 'merge_ready': return `waiting for a ${text(e.awaiting)}: ${(e.blockers as string[] | undefined)?.join('; ') ?? ''}`;
    default: return '';
  }
};

export function EventLog() {
  const { seen } = useRun();
  const log = useRef<HTMLDivElement>(null);
  // follow the newest line, like a build log
  useEffect(() => { log.current?.scrollTo({ top: log.current.scrollHeight }); }, [seen.length]);
  return (
    <section className="card" aria-label="Event stream">
      <div className="card-h">Event stream<span className="end num">{seen.length || ''}</span></div>
      {seen.length ? (
        <div className="log" role="log" aria-live="polite" ref={log}>
          {seen.map((e, i) => (
            <motion.div key={i} initial={{ opacity: 0, x: -4 }} animate={{ opacity: 1, x: 0 }}>
              <span className="t num">{clock(e.ts)}</span>
              <span className={e.type === 'retest' ? 'green' : e.type === 'flag_check' || e.type === 'red_finding' ? 'red' : 'soft'}>{e.type}</span>
              <span>{describe(e)}</span>
            </motion.div>
          ))}
        </div>
      ) : <div className="empty"><strong>No events yet</strong>Ask NEO to attack the demo app</div>}
    </section>
  );
}
