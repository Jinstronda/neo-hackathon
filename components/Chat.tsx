'use client';
import { useChat } from '@ai-sdk/react';
import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useRef } from 'react';
import { useRun } from './RunProvider';

const prompts = ['Attack our demo app', 'What did you find?', 'Fix it', 'Approved'];
const toolLabel: Record<string, string> = { attack_demo_app: 'Started the red team', read_findings: 'Read the findings', fix_finding: 'Patched and retested', approve_merge: 'Recorded the approval', run_status: 'Read the run' };

export function Chat() {
  const { play } = useRun();
  const { messages, input, handleInputChange, handleSubmit, append, status, data } = useChat({ api: '/api/chat' });
  const handled = useRef(0);
  const end = useRef<HTMLDivElement>(null);
  // the agent's tool calls arrive as data parts; each one starts the matching engine phase on screen
  useEffect(() => {
    for (const part of (data ?? []).slice(handled.current) as { action?: string }[]) {
      if (part?.action === 'attack') play('red');
      if (part?.action === 'fix') play('blue');
      if (part?.action === 'approve') play('merge');
    }
    handled.current = data?.length ?? 0;
  }, [data, play]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }); }, [messages]);
  const busy = status === 'submitted' || status === 'streaming';
  return (
    <section className="card chat" aria-label="Chat with NEO">
      <div className="card-h">NEO<span className="end">{busy ? <span className="shimmer-text">Thinking</span> : 'Eve agent'}</span></div>
      <div className="msgs">
        <AnimatePresence initial={false}>
          {messages.map((m) => (
            <motion.div key={m.id} className={`msg ${m.role === 'user' ? 'user' : 'neo'}`} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.24 }}>
              <span className="who">{m.role === 'user' ? 'You' : 'NEO'}</span>
              {m.parts.map((p, i) => p.type === 'text' ? <span key={i} className="body">{p.text.replace(/`/g, '')}</span>
                : p.type === 'tool-invocation' ? <span key={i} className="tool">{toolLabel[p.toolInvocation.toolName] ?? p.toolInvocation.toolName}</span> : null)}
            </motion.div>
          ))}
        </AnimatePresence>
        {!messages.length && <div className="empty"><strong>Talk to NEO</strong>It attacks a twin of the demo app, patches it and proves the fix</div>}
        <div ref={end} />
      </div>
      <div>
        <div className="suggest">{prompts.map((p) => <button key={p} type="button" disabled={busy} onClick={() => append({ role: 'user', content: p })}>{p}</button>)}</div>
        <form className="composer" onSubmit={handleSubmit}>
          <input value={input} onChange={handleInputChange} placeholder="Message NEO" aria-label="Message NEO" autoComplete="off" />
          <button className="btn primary" type="submit" disabled={busy || !input.trim()}>Send</button>
        </form>
      </div>
    </section>
  );
}
