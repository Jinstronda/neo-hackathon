"""Shared fixtures. Adds demo-target to the path so the reference exploits (which
import `_http`) load, and gives tests a one-call boot+exploit+check helper."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "demo-target"))

from neo.harness import scenarios, target  # noqa: E402


def pytest_configure(config):
    for mark in ("prepatch: exploit works on the vulnerable target",
                 "postpatch: exploit is dead after the fix",
                 "network: needs the live CVE feeds"):
        config.addinivalue_line("markers", mark)


@pytest.fixture(params=scenarios.ALL, ids=[s.name for s in scenarios.ALL])
def scenario(request):
    return request.param


def exploit_and_check(scenario, state_dir, app_path=target.APP):
    """Boot the target (optionally a patched copy), run the reference exploit,
    return the server-side check verdict read from the run's event log."""
    with target.session(state_dir, app_path=app_path) as tgt:
        scenario.exploit(tgt)
    return scenario.check(state_dir)
