'use client';
import { useChat } from '@ai-sdk/react';
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { view, type View } from '@/lib/state';
import type { Phase, Run, RunEvent, Source } from '@/lib/types';
type Chat = ReturnType<typeof useChat>;
interface RunContext { operator: string | null; chat: Chat; run: Run | null; seen: RunEvent[]; view: View | null; source: Source | null; playing: Phase | null; play: (phase: Phase) => void; reset: () => void }
const Ctx = createContext<RunContext | null>(null);

// Holds the events seen so far. A phase streams from /api/stream (SSE); screens derive from `seen` only.
export function RunProvider({ children, initial, operator }: { children: ReactNode; initial: Run | null; operator: string | null }) {
  const [run, setRun] = useState<Run | null>(initial);
  const [seen, setSeen] = useState<RunEvent[]>([]);
  const [playing, setPlaying] = useState<Phase | null>(null);
  const source = useRef<EventSource | null>(null);
  useEffect(() => { if (!initial) fetch('/api/run').then((r) => r.json()).then(setRun).catch(() => setRun(null)); }, [initial]);
  const play = useCallback((phase: Phase) => {
    source.current?.close();
    if (phase === 'red') setSeen([]);
    setPlaying(phase);
    const es = new EventSource(`/api/stream?phase=${phase}`);
    source.current = es;
    es.onmessage = (message) => {
      const event = JSON.parse(message.data) as RunEvent;
      setSeen((old) => old.some((e) => e.ts === event.ts && e.type === event.type) ? old : [...old, event]);
    };
    es.addEventListener('done', () => { es.close(); setPlaying(null); });
    es.onerror = () => { es.close(); setPlaying(null); };
  }, []);
  // the chat lives here, above the routes, so moving between tabs keeps the conversation and its stream
  const chat = useChat({ api: '/api/chat' });
  const handled = useRef(0);
  useEffect(() => {
    for (const part of (chat.data ?? []).slice(handled.current) as { action?: string }[]) {
      if (part?.action === 'attack') play('red');
      if (part?.action === 'fix') play('blue');
      if (part?.action === 'approve') play('merge');
    }
    handled.current = chat.data?.length ?? 0;
  }, [chat.data, play]);
  const reset = useCallback(() => { source.current?.close(); setSeen([]); setPlaying(null); }, []);
  const value = useMemo(() => ({ operator, chat, run, seen, playing, play, reset, source: run?.source ?? null, view: run ? view(run.run, seen) : null }), [operator, chat, run, seen, playing, play, reset]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useRun(): RunContext {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useRun outside RunProvider');
  return ctx;
}
