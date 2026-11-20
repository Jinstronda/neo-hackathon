"""Terminal view: the loop's newer events each get a narrated line of their own,
event-derived text is sanitized before it reaches a terminal, and a run that
stops at fix approval closes with a summary that has no empty rows."""
import io

import pytest

from neo import term

WATCH = [
    ("watch_tick", {"cycle": 3, "new_matches": 1, "kev_source": "live(1484)+staged",
                    "next_in_s": 300}),
    ("watch_trigger", {"cve": "CVE-2020-14343", "package": "pyyaml", "version": "5.3.1",
                       "run_id": "watch-1"}),
    ("watch_error", {"cycle": 4, "error": "URLError: feed down"}),
]
FIX = [
    ("fix_approval", {"approved": True, "by": "human"}),
    ("fix_attempt", {"attempt": 1, "of": 3, "source": "model", "ok": False,
                     "exploits_dead": {"sql-injection": True, "ssrf-metadata": False},
                     "legit_login_ok": True, "error": "anchor not found"}),
    ("fix_attempt", {"attempt": 2, "of": 3, "source": "canonical", "ok": True,
                     "exploits_dead": {"sql-injection": True, "ssrf-metadata": True},
                     "legit_login_ok": True}),
]
RED = [
    ("radar_match", {"cve": "CVE-2020-14343", "package": "pyyaml", "version": "5.3.1",
                     "kev": True, "epss": 0.9, "osv": ["GHSA-1"], "reachable": True}),
    ("red_start", {"twin_id": "twin-1", "models": ["model-1", "model-2"]}),
    ("red_finding", {"finding_id": "A1", "cls": "sql-injection", "location": "POST /login",
                     "found_by": ["model-1"], "confirmed_by": "server-side flag check",
                     "response": []}),
]


@pytest.fixture(autouse=True)
def plain(monkeypatch):
    monkeypatch.setattr(term, "COLOR", False)


def _print(events):
    out = io.StringIO()
    p = term.Printer(out, run_id="t")
    for i, (etype, fields) in enumerate(events):
        p.event({"type": etype, "ts": 100.0 + i, **fields})
    return p, out


def test_new_events_have_their_own_printer():
    _, out = _print(WATCH + FIX)
    text = out.getvalue()
    assert "cycle 3  1 new KEV matches in the SBOM  KEV live(1484)+staged" in text
    assert "CVE-2020-14343  pyyaml 5.3.1  -> run watch-1" in text
    assert "cycle 4  error: URLError: feed down" in text
    assert "fix approved by human" in text
    assert "attempt 1/3  model patch  rejected" in text
    assert "ssrf-metadata ALIVE" in text and "error: anchor not found" in text
    assert "attempt 2/3  canonical patch  verified" in text
    assert text.count("STEP 3") == 1
    # the generic fallback prints key=value; none of these events should reach it
    assert "approved=" not in text and "new_matches=" not in text


def test_event_text_is_sanitized():
    _, out = _print([
        ("watch_trigger", {"cve": "CVE-1\x1b[2J", "package": "x\x07", "version": "1",
                           "run_id": "r\x1b]0;owned\x07"}),
        ("fix_attempt", {"attempt": 1, "of": 1, "source": "model\x1b[31m", "ok": False,
                         "exploits_dead": {"sqli\x1b[8m": False}, "legit_login_ok": False}),
        ("fix_approval", {"approved": False, "by": "human\x1b[1A"}),
    ])
    text = out.getvalue()
    assert "\x1b" not in text and "\x07" not in text


def test_declined_fix_summary_has_no_empty_rows():
    p, out = _print(RED + [("fix_approval", {"approved": False, "by": "human"})])
    p.summary()
    box = out.getvalue().split("┌", 1)[1]
    assert "not approved; blue did not run" in box
    assert "proven      1 exploits: sql-injection" in box
    assert "None" not in box and "patch " not in box and "reviews" not in box
