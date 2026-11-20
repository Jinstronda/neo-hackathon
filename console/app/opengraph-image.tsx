import { ImageResponse } from 'next/og';

export const alt = 'NEO: the exploit lands on the twin, the patched twin stops it';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export default function Image() {
  return new ImageResponse(
    <div style={{ width: '100%', height: '100%', background: '#000', color: '#ededed', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: 72, fontFamily: 'sans-serif' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 20, fontSize: 56, fontWeight: 700 }}>
        <svg width="56" height="56" viewBox="0 0 24 24"><path d="M12 2 22 20H2L12 2Z" fill="#ededed" /></svg>NEO
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 18, fontSize: 40, fontFamily: 'monospace' }}>
        <span style={{ color: '#ff6166' }}>twin before patch  objective_complete=true</span>
        <span style={{ color: '#62c073' }}>rebuilt twin       objective_complete=false</span>
      </div>
    </div>,
    size,
  );
}
