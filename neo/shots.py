"""One evidence PNG per loop step into screenshots/. Terminal-styled HTML panels
for the radar / flag-check / review / gate output, and a real headless screenshot
of the live PR page, captured with agent-browser (Chrome for Testing). Best
effort: a backend miss is logged and skipped, it never fails the run."""
import html
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SHOTS = REPO / "screenshots"
PANELS = SHOTS / "_panels"

_CSS = """
*{margin:0;box-sizing:border-box}
body{background:#0b0e14;font:15px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace}
#panel{background:#0b0e14;color:#c7d0e0;padding:34px 40px;width:1080px}
h1{font-size:15px;color:#8a93a6;font-weight:600;letter-spacing:.14em;text-transform:uppercase;
margin-bottom:22px}
.row{padding:3px 0;white-space:pre-wrap}
.k{color:#7f8aa0} .red{color:#ff6b6b;font-weight:700} .grn{color:#55d18e;font-weight:700}
.y{color:#e4c96b} .b{color:#6ea8ff} .dim{color:#5a6477} .w{color:#eef2f8;font-weight:600}
.hr{border:0;border-top:1px solid #1c2230;margin:16px 0}
"""


def _render(lines):
    out = []
    for ln in lines:
        out.append(f'<div class="row">{ln}</div>' if ln else '<hr class="hr">')
    return "\n".join(out)


def _ab(*args, timeout=150):
    return subprocess.run(["agent-browser", *args], capture_output=True, text=True,
                          timeout=timeout)


def panel(name, title, lines):
    PANELS.mkdir(parents=True, exist_ok=True)
    doc = (f"<!doctype html><meta charset=utf-8><style>{_CSS}</style>"
           f'<div id="panel"><h1>{html.escape(title)}</h1>{_render(lines)}</div>')
    p = PANELS / f"{name}.html"
    p.write_text(doc)
    return shot("file://" + str(p), name, selector="#panel")


def shot(url, name, *, selector=None):
    out = SHOTS / f"{name}.png"
    try:
        _ab("open", url)
        args = ["screenshot"]
        if selector:
            args.append(selector)
        args.append(str(out))
        r = _ab(*args)
        if out.exists() and out.stat().st_size > 0:
            return out
        return None if r.returncode == 0 else None
    except (subprocess.SubprocessError, OSError):
        return None


def esc(x):
    return html.escape(str(x))
