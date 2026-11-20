"""Shared server-side event reader for the flag checks. The checks decide
success from this log alone, never from an agent's report."""
import json
from pathlib import Path


def read(state_dir):
    path = Path(state_dir) / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def of(events, etype):
    return [e for e in events if e.get("type") == etype]
