'use client';
import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useRef } from 'react';
import { useRun } from './RunProvider';
import { clock, text } from '@/lib/types';

const roleName = { red: 'Attack', blue: 'Patch', reviewer: 'Review' } as const;
const stateWord = { idle: 'Idle', working: 'Working', done: 'Done' } as const;

export function Board({ compact }: { compact?: boolean }) {
  const { view } = useRun();
  if (!view) return <div className="card"><div className="card-h">Agents</div><div style={{ padding: 16, display: 'grid', gap: 10 }}><div className="skel" /><div className="skel" style={{ width: '60%' }} /></div></div>;
  const busy = view.agents.filter((a) => a.busy).length;
  const done = view.agents.filter((a) => a.status === 'done').length;
  return (
    <section className="card" aria-label="Agents">
      <div className="card-h">Agents<span className="end">{busy ? `${busy} working` : `${done}/${view.agents.length} done`}</span></div>
      <div className={`agents${compact ? ' compact' : ''}`}>
        {view.agents.map((agent, index) => (
          <motion.div key={agent.id} className={`agent is-${agent.status}`} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.04, duration: 0.3 }}>
            <div className="agent-h">
              <b>{agent.label}</b>
              <span className="role">{roleName[agent.role]}</span>
              <span className={`astate end ${agent.status}`}>{agent.busy ? <span className="shimmer-text">Working</span> : stateWord[agent.status]}</span>
            </div>
            <span className="asub mono">{agent.sub}</span>
            <div className="atrace">
              <AnimatePresence initial={false}>
                {agent.trace.slice(compact ? -2 : -3).map((line) => (
                  <motion.span key={`${line.ts}-${line.label}`} layout initial={{ opacity: 0, x: -4 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} className={line.tone ?? 'soft'}>{line.label}</motion.span>
                ))}
                {agent.busy && <motion.span key="working" layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="shimmer-text">{agent.role === 'red' ? 'Driving the target' : agent.role === 'blue' ? 'Patching' : 'Reading the diff'}</motion.span>}
                {!agent.trace.length && !agent.busy && <span key="idle" className="soft">Waiting</span>}
              </AnimatePresence>
            </div>
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
    case 'blue_patch': return `${e.pr_number ? `PR #${text(e.pr_number)} ` : ''}${text(e.branch)}`;
    case 'review': return `${text(e.reviewer)} ${text(e.verdict)}`;
    case 'retest': return `objective_complete=${text(e.objective_complete)} ${text(e.status)}`;
    case 'tests': return `${text(e.passed)}/${text(e.total)} passed`;
    case 'metrics': return `${text(e.minutes_exploit_to_fix)} min, $${text(e.cost_usd)}`;
    case 'merge': return `${e.pr_number ? `PR #${text(e.pr_number)} ` : ''}merged by ${text(e.by)}`;
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
        <div className="log" role="log" aria-live="polite" tabIndex={0} ref={log}>
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
