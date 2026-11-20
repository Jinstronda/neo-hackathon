"""Tiny .env loader so scripts and the engine read the gateway key and twin
creds without a dependency. Values already in the environment win."""
import os
from pathlib import Path


def load(path=None):
    p = Path(path or Path(__file__).resolve().parent.parent / ".env")
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())
