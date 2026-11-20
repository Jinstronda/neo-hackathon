'use client';
import { useEffect, useState } from 'react';

// Unified diff with Python highlighting: shiki tokenizes the code lines, the +/- gutter keeps the diff colors.
type Token = { content: string; color?: string };
const meta = (line: string) => /^(diff |index |--- |\+\+\+ |@@)/.test(line);
const tone = (line: string) => line.startsWith('@@') ? 'hunk' : meta(line) ? 'meta' : line.startsWith('+') ? 'add' : line.startsWith('-') ? 'del' : undefined;

export function Diff({ diff }: { diff: string }) {
  const lines = diff.replace(/\n$/, '').split('\n');
  const [tokens, setTokens] = useState<Token[][] | null>(null);
  useEffect(() => {
    let live = true;
    import('shiki').then(({ codeToTokens }) => codeToTokens(lines.map((l) => meta(l) ? '' : l.slice(1)).join('\n'), { lang: 'python', theme: 'github-dark-default' }))
      .then((r) => { if (live) setTokens(r.tokens); }).catch(() => undefined);
    return () => { live = false; };
  }, [diff]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <pre className="code diff" aria-label="Patch diff" tabIndex={0}>
      {lines.map((line, i) => (
        <div key={i} className={tone(line)}>
          {meta(line) || !tokens?.[i] ? line || ' ' : <><span className="gutter">{line[0]}</span>{tokens[i].map((t, j) => <span key={j} style={{ color: t.color }}>{t.content}</span>)}</>}
        </div>
      ))}
    </pre>
  );
}
