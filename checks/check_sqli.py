#!/usr/bin/env python3
"""Flag check for Bug A (SQL-injection auth bypass). Server-side only.

The admin password is randomized per run, so a login_success with role=admin can
only come from injection. That event is the objective.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _events import of, read  # noqa: E402


def check(state_dir):
    events = read(state_dir)
    admin_logins = [e for e in of(events, "login_success")
                    if e.get("detail", {}).get("role") == "admin"]
    return {
        "scenario": "sql-injection",
        "objective_complete": bool(admin_logins),
        "evidence": [{"type": "login_success", "role": "admin",
                      "payload": e.get("detail", {}).get("submitted")}
                     for e in admin_logins[:3]],
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    print(json.dumps(check(ap.parse_args().state)))
