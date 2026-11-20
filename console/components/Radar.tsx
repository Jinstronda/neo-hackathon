'use client';
import { motion } from 'motion/react';
import { useRun } from './RunProvider';
import { clock, num, text } from '@/lib/types';

// Daily matches of CISA KEV, EPSS and OSV against the demo app's SBOM, as the engine reports them.
export function Radar() {
  const { run, seen } = useRun();
  if (!run) return <div className="card" style={{ padding: 16 }}><div className="skel" /></div>;
  // a live run brings its own radar pass; before one, the bundled run's matches show
  const live = seen.filter((e) => e.type === 'radar_match');
  const matches = live.length ? live : run.events.filter((e) => e.type === 'radar_match');
  return (
    <section className="card">
      {matches.length ? (
        <table>
          <thead><tr><th>Advisory</th><th>Package</th><th>KEV</th><th>EPSS</th><th className="hide-sm">OSV</th><th>Reachable</th><th className="hide-sm">Matched</th></tr></thead>
          <tbody>{matches.map((m, i) => (
            <motion.tr key={text(m.cve)} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
              <td className="mono">{text(m.cve)}</td>
              <td><span className="mono">{text(m.package)}</span> <span className="muted">{text(m.version)}</span></td>
              <td className={m.kev === true || m.kev === 'True' ? 'red' : 'muted'}>{m.kev === true || m.kev === 'True' ? (m.kev_staged || /staged/.test(String(m.kev_source ?? '')) ? 'Listed, staged' : 'Listed') : 'No'}</td>
              <td className={`num ${num(m.epss) >= 0.5 ? 'red' : ''}`}>{(num(m.epss) * 100).toFixed(1)}%</td>
              <td className="mono hide-sm">{text(m.osv)}</td>
              <td className={m.reachable === true || m.reachable === 'True' ? 'amber' : 'muted'}>{m.reachable === true || m.reachable === 'True' ? 'Yes' : 'No'}</td>
              <td className="num muted hide-sm">{clock(m.ts)}</td>
            </motion.tr>
          ))}</tbody>
        </table>
      ) : <div className="empty"><strong>No matches today</strong>Nothing in the SBOM is on KEV, EPSS or OSV</div>}
    </section>
  );
}
