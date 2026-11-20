export const metadata = { title: 'Demo' };
import { Body } from './Body';

export default function Demo() {
  return (
    <div className="page">
      <div className="head"><h1>Live run</h1><span className="end muted mono">2026-11-20 · EU</span></div>
      <Body />
    </div>
  );
}
