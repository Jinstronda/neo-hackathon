"""Tiny .env loader so every entry point reads the gateway key, the red swarm ids
and the twin creds without a dependency. Values already in the environment win."""
import os
from pathlib import Path

DEFAULT = Path(__file__).resolve().parent.parent / ".env"


def load(path: str | Path | None = None) -> None:
    p = Path(path or DEFAULT)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip().removeprefix("export ").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), _unquote(v.strip()))


def _unquote(v: str) -> str:
    # KEY="a,b" and KEY='a,b' mean a,b, as in a shell
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'" else v
