'use client';
import { useEffect, useRef } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useRun } from './RunProvider';

// Stage path on one key. Space, Right or PageDown (clickers) runs the next beat; Left or PageUp goes back a screen;
// 1-4 jump to a tab. A beat that talks to NEO waits until NEO and the engine stream are idle.
type Beat = { go: string; say?: string };
const beats: Beat[] = [
  { go: '/', say: 'Attack our demo app' },
  { go: '/', say: 'What did you find?' },
  { go: '/incident' },
  { go: '/', say: 'Fix it' },
  { go: '/incident' },
  { go: '/', say: 'Approved' },
  { go: '/numbers' },
  { go: '/radar' },
];
const tabs = ['/', '/incident', '/radar', '/numbers'];

export function Presenter() {
  const router = useRouter();
  const path = usePathname();
  const { chat, playing } = useRun();
  const at = useRef(0);
  const busy = chat.status === 'streaming' || chat.status === 'submitted' || playing !== null;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target?.closest('input, textarea, [contenteditable]') || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === ' ' || e.key === 'ArrowRight' || e.key === 'PageDown') {
        e.preventDefault();
        const beat = beats[at.current];
        if (!beat || (beat.say && busy)) return;
        if (path !== beat.go) router.push(beat.go);
        if (beat.say) void chat.append({ role: 'user', content: beat.say });
        at.current += 1;
      } else if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
        e.preventDefault();
        router.back();
      } else if (/^[1-4]$/.test(e.key)) router.push(tabs[Number(e.key) - 1]);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [busy, chat, path, router]);
  return null;
}
