#!/usr/bin/env python3
"""Flag check for Bug B (SSRF -> metadata -> credential reuse). Server-side only.

The full chain is proven: the internal metadata service was reached, the leaked
key was presented to the admin API, and the flag was read.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _events import of, read  # noqa: E402


def check(state_dir):
    events = read(state_dir)
    internal = of(events, "internal_fetch")
    key_used = of(events, "admin_key_used")
    flag = of(events, "flag_read")
    complete = bool(internal) and bool(key_used) and bool(flag)
    return {
        "scenario": "ssrf-metadata",
        "objective_complete": complete,
        "evidence": [
            {"type": "internal_fetch", "count": len(internal)},
            {"type": "admin_key_used", "count": len(key_used)},
            {"type": "flag_read", "count": len(flag)},
        ],
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    print(json.dumps(check(ap.parse_args().state)))
