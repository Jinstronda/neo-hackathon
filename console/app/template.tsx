// route change: CSS fade and lift on each navigation (transform + opacity, reduced-motion aware in globals.css)
export default function Template({ children }: { children: React.ReactNode }) {
  return <div className="enter">{children}</div>;
}
