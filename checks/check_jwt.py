#!/usr/bin/env python3
"""Flag check for Bug C (weak-JWT-secret forgery). Server-side only.

The server never issues an admin token through the guest path and tracks the jti
of every token it signs. A jwt_forged_admin event means an admin-role token with
a valid signature arrived that the server never issued: a forgery.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _events import of, read  # noqa: E402


def check(state_dir) -> dict:
    events = read(state_dir)
    forged = of(events, "jwt_forged_admin")
    return {
        "scenario": "weak-jwt-secret",
        "objective_complete": bool(forged),
        "evidence": [{"type": "jwt_forged_admin", "sub": e.get("detail", {}).get("sub")}
                     for e in forged[:3]],
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    print(json.dumps(check(ap.parse_args().state)))
