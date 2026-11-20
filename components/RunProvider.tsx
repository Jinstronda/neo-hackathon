'use client';
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { view, type View } from '@/lib/state';
import type { Phase, Run, RunEvent, Source } from '@/lib/types';
interface RunContext { run: Run | null; seen: RunEvent[]; view: View | null; source: Source | null; playing: Phase | null; play: (phase: Phase) => void; reset: () => void }
const Ctx = createContext<RunContext | null>(null);

// Holds the events seen so far. A phase streams from /api/stream (SSE); screens derive from `seen` only.
export function RunProvider({ children }: { children: ReactNode }) {
  const [run, setRun] = useState<Run | null>(null);
  const [seen, setSeen] = useState<RunEvent[]>([]);
  const [playing, setPlaying] = useState<Phase | null>(null);
  const source = useRef<EventSource | null>(null);
  useEffect(() => { fetch('/api/run').then((r) => r.json()).then(setRun).catch(() => setRun(null)); }, []);
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
  const reset = useCallback(() => { source.current?.close(); setSeen([]); setPlaying(null); }, []);
  const value = useMemo(() => ({ run, seen, playing, play, reset, source: run?.source ?? null, view: run ? view(run.run, seen) : null }), [run, seen, playing, play, reset]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useRun(): RunContext {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useRun outside RunProvider');
  return ctx;
}
