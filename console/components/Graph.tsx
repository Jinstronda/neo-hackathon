'use client';
import { motion } from 'motion/react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useRun } from './RunProvider';
import { graph, LANES, type GNode } from '@/lib/graph';

const PAD = 14, TOP = 34;
const ease = [0.16, 1, 0.3, 1] as const;
let ctx: CanvasRenderingContext2D | null = null;
// trim to the pixel width the label really has, measured with the page's own font
function fit(s: string, max: number, font: string) {
  ctx ??= document.createElement('canvas').getContext('2d');
  if (!ctx) return s;
  ctx.font = font;
  if (ctx.measureText(s).width <= max) return s;
  let t = s;
  while (t.length > 1 && ctx.measureText(`${t}…`).width > max) t = t.slice(0, -1);
  return `${t}…`;
}
const family = (v: string) => getComputedStyle(document.documentElement).getPropertyValue(v).trim() || 'sans-serif';

type Box = { x: number; y: number };
function layout(nodes: GNode[], w: number, h: number) {
  const nodeW = Math.max(118, Math.min(176, (w - 2 * PAD) / LANES.length - 24));
  const nodeH = nodeW >= 160 ? 54 : 46;
  const step = (w - 2 * PAD - nodeW) / (LANES.length - 1);
  const pos = new Map<string, Box>();
  LANES.forEach((_, c) => {
    const col = nodes.filter((n) => n.col === c);
    const avail = h - TOP - PAD;
    const gap = Math.min(nodeH * 2, (avail - nodeH) / Math.max(1, col.length - 1));
    const y0 = TOP + (avail - nodeH - gap * (col.length - 1)) / 2;
    col.forEach((n, i) => pos.set(n.id, { x: PAD + c * step, y: y0 + i * gap }));
  });
  return { pos, nodeW, nodeH, step };
}

function edgePath(a: Box, b: Box, nodeW: number, nodeH: number) {
  if (Math.abs(a.x - b.x) < 1) return `M ${a.x + nodeW / 2} ${a.y + nodeH} C ${a.x + nodeW / 2} ${a.y + nodeH + 10}, ${b.x + nodeW / 2} ${b.y - 10}, ${b.x + nodeW / 2} ${b.y}`;
  const x1 = a.x + nodeW, y1 = a.y + nodeH / 2, x2 = b.x, y2 = b.y + nodeH / 2, dx = (x2 - x1) / 2;
  return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
}

export function Graph() {
  const { run, seen, view } = useRun();
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [pinned, setPinned] = useState<string | null>(null);
  useEffect(() => {
    if (!box.current) return;
    const ro = new ResizeObserver(([entry]) => setSize({ w: entry.contentRect.width, h: entry.contentRect.height }));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);
  const g = useMemo(() => (run && view ? graph(run.run, seen, view) : { nodes: [], edges: [], landed: 0, dead: 0 }), [run, seen, view]);
  const { pos, nodeW, nodeH } = layout(g.nodes, size.w, size.h);
  // follow the newest entity unless the operator pinned one
  const newest = g.nodes.reduce<GNode | undefined>((best, n) => (!best || n.ts >= best.ts ? n : best), undefined);
  const sel = g.nodes.find((n) => n.id === pinned) ?? newest;
  const pick = (id: string) => setPinned((p) => (p === id ? null : id));
  const big = nodeH > 46, small = nodeW < 140;
  const tSize = big ? 15 : small ? 12 : 13, sSize = big ? 12 : small ? 10.5 : 11;
  const label = (s: string, mono: boolean) => (size.w ? fit(s, nodeW - 20, mono ? `${sSize}px ${family('--font-geist-mono')}` : `500 ${tSize}px ${family('--font-geist-sans')}`) : s);

  return (
    <section className="card graph" aria-label="Attack graph">
      <div className="card-h">Attack graph<span className="end num">{g.landed ? `${g.landed} landed${g.dead ? ` · ${g.dead} dead after patch` : ''}` : ''}</span></div>
      <div className="gwrap">
        <div className="gin" ref={box}>
          {size.w > 0 && (
            <svg width={size.w} height={size.h} viewBox={`0 0 ${size.w} ${size.h}`}>
              {LANES.map((lane, c) => <text key={lane} className="glane" x={PAD + c * ((size.w - 2 * PAD - nodeW) / (LANES.length - 1))} y={18}>{lane}</text>)}
              {g.edges.map((e) => {
                const a = pos.get(e.from), b = pos.get(e.to);
                if (!a || !b) return null;
                const d = edgePath(a, b, nodeW, nodeH);
                return (
                  <g key={`${e.from}>${e.to}`}>
                    <motion.path className={`gedge ${e.tone}`} initial={{ d, pathLength: 0, opacity: 0 }} animate={{ d, pathLength: 1, opacity: 1 }} transition={{ duration: 0.6, ease }} />
                    {e.flowing && <path className="gflow" d={d} />}
                  </g>
                );
              })}
              {g.nodes.map((n) => {
                const p = pos.get(n.id)!;
                return (
                  <motion.g key={n.id} className={`gn${n.working ? ' working' : ''}${sel?.id === n.id ? ' sel' : ''}`} role="button" tabIndex={0}
                    aria-label={`${LANES[n.col]}: ${n.title}, ${n.sub}`} aria-pressed={pinned === n.id}
                    initial={{ opacity: 0, x: p.x, y: p.y + 6 }} animate={{ opacity: 1, x: p.x, y: p.y }} transition={{ duration: 0.45, ease }}
                    onClick={() => pick(n.id)} onKeyDown={(e) => { if (e.key === 'Enter') pick(n.id); }}>
                    <title>{`${n.title} · ${n.sub}`}</title>
                    <rect className={`gnode ${n.tone}`} width={nodeW} height={nodeH} rx={8} />
                    <text className={`gt ${n.tone}`} x={10} y={big ? 22 : 19} style={{ fontSize: tSize }}>{label(n.title, false)}</text>
                    <text className="gs" x={10} y={big ? 41 : 35} style={{ fontSize: sSize }}>{label(n.sub, true)}</text>
                  </motion.g>
                );
              })}
            </svg>
          )}
          {!g.nodes.length && <div className="empty gempty"><strong>No run yet</strong>Ask NEO to attack the demo app</div>}
        </div>
      </div>
      <div className="ginsp">
        {sel && <>
          <b className={sel.tone === 'plain' ? '' : sel.tone}>{sel.title}</b>
          <dl>{sel.facts.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
          {sel.href && <a className="btn end" href={sel.href} target="_blank" rel="noreferrer">Open PR</a>}
        </>}
      </div>
    </section>
  );
}
