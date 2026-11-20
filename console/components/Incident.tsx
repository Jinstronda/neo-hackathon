'use client';
import { AnimatePresence, motion } from 'motion/react';
import { useRun } from './RunProvider';
import { Timeline } from './Board';
import { Diff } from './Diff';
import { objectiveReached } from '@/lib/state';
import { clock, text, type RunEvent } from '@/lib/types';

function Twin({ title, twin, check, request, tally }: { title: string; twin?: RunEvent; check?: RunEvent; request?: string; tally?: string }) {
  const reached = objectiveReached(check);
  const tone = !check ? '' : reached ? 'red' : 'green';
  return (
    <section className={`card twin${tone ? ` tint-${tone}` : ""}`} aria-label={title}>
      <div className="agent-h"><b>{title}</b><span className="role mono">{twin ? text(twin.twin_id) : ''}</span></div>
      <AnimatePresence mode="wait">
        {check ? (
          <motion.div key="v" initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.36, ease: [0.16, 1, 0.3, 1] }} style={{ display: 'grid', gap: 12 }}>
            <span className={`verdict ${tone}`}>{reached ? 'Exploit landed' : 'Exploit failed'}</span>
            <dl className="kv">
              <dt>Flag check</dt><dd className="mono">objective_complete={String(reached)}</dd>
              <dt>Scenario</dt><dd>{text(check.scenario)}</dd>
              {tally && <><dt>Exploits</dt><dd>{tally}</dd></>}
              {twin?.image ? <><dt>Image</dt><dd className="mono">{text(twin.image)}</dd></> : null}
              <dt>Checked</dt><dd className="num">{clock(check.ts)}</dd>
            </dl>
            {request && <pre className="code">{request}</pre>}
          </motion.div>
        ) : <motion.div key="e" className="empty" exit={{ opacity: 0 }}>{twin ? <span className="shimmer-text">Running the exploit</span> : <strong>Not started</strong>}</motion.div>}
      </AnimatePresence>
    </section>
  );
}

export function Incident() {
  const { view } = useRun();
  if (!view) return <div className="card" style={{ padding: 16 }}><div className="skel" /></div>;
  const [before, after] = [view.twins.find((t) => t.type === 'twin_create') ?? view.started, view.twins.find((t) => t.type === 'twin_deploy')];
  const finding = view.findings[0];
  const n = view.proof.length;
  const landed = view.proof.filter((p) => p.before).length, dead = view.proof.filter((p) => p.after && !objectiveReached(p.after)).length;
  const payload = (view.pre?.evidence as { payload?: string; role?: string }[] | undefined)?.find((e) => e.payload);
  const request = [finding?.request, payload && `payload  ${payload.payload}${payload.role ? `  ->  role ${payload.role}` : ''}`].filter(Boolean).join('\n\n');
  return (
    <>
      <div className="twins">
        <Twin title="Twin before the patch" twin={before} check={view.pre} request={request} tally={n ? `${landed} of ${n} landed` : undefined} />
        <Twin title="Rebuilt twin" twin={after} check={view.post} tally={n && view.post ? `${dead} of ${n} failed` : undefined} />
      </div>
      <div className="split-3">
        <section className="card" aria-label="Patch">
          <div className="card-h">{view.patch?.pr_number ? `PR #${text(view.patch.pr_number)}` : 'Patch'}<span className="end mono">{view.patch ? text(view.patch.branch) : ''}</span></div>
          {view.patch ? (
            <div style={{ padding: 16, display: 'grid', gap: 12 }}>
              {(view.patch.commits as { msg: string }[] | undefined)?.map((c) => <span key={c.msg} className="mono">{c.msg}</span>)}
              <Diff diff={text(view.patch.diff)} />
              {view.reviews.map((r) => (
                <motion.dl key={text(r.reviewer)} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} className="kv">
                  <dt className="soft">{text(r.reviewer)}</dt>
                  <dd><span className={r.verdict === 'approve' ? 'green' : 'red'}>{r.verdict === 'approve' ? 'Approved' : 'Changes requested'}</span> <span className="soft">{text(r.comment)}</span></dd>
                </motion.dl>
              ))}
              {view.merge && <span className="green">Approved by a human at {clock(view.merge.ts)}</span>}
            </div>
          ) : <div className="empty"><strong>No patch yet</strong>Tell NEO to fix it</div>}
        </section>
        <Timeline />
      </div>
    </>
  );
}
