"""neo watch: the first cycle runs the loop once per new KEV match, a repeat scan
runs nothing, the seen-set survives a restart, and a run (or a scan) that raises is
journaled without stopping the daemon; the failed match is retried next cycle.
Scan and loop are fakes: no network, no LLM."""
import json
import re

import pytest

from neo import config, watch

YAML = {"cve": "CVE-2020-14343", "package": "PyYAML", "version": "5.3.1", "kev": True}
JINJA = {"cve": "CVE-2024-0001", "package": "Jinja2", "version": "2.10", "kev": True}
NOISE = {"cve": "CVE-2021-9999", "package": "requests", "version": "2.0", "kev": False}


def scan_of(*matches):
    return lambda: {"kev_source": "staged-only", "matches": [dict(m) for m in matches]}


def recorder(fail=()):
    """A fake orchestrator.loop that records each call and raises for the CVEs in fail."""
    def run_loop(**kw):
        run_loop.calls.append(kw)
        if any(cve in kw["run_id"] for cve in fail):
            raise RuntimeError("twin unreachable")
        return {"id": kw["run_id"]}
    run_loop.calls = []
    return run_loop


def once(root, scan, run_loop):
    return watch.watch(once=True, scan=scan, run_loop=run_loop, root=root, live=False)


def events(root, kind):
    rows = [json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()]
    return [r for r in rows if r["type"] == kind]


def state(root):
    return json.loads((root / "state.json").read_text())


def test_first_cycle_triggers_once_per_new_kev_match(tmp_path):
    run_loop = recorder()
    stats = once(tmp_path, scan_of(YAML, JINJA, NOISE), run_loop)
    assert stats == {"cycles": 1, "triggered": 2, "errors": 0, "stopped": False}
    ids = [c["run_id"] for c in run_loop.calls]
    assert re.fullmatch(r"watch-CVE-2020-14343-\d{12}", ids[0])
    assert re.fullmatch(r"watch-CVE-2024-0001-\d{12}", ids[1])
    assert all(c["repo"] is None and c["screenshots"] is False for c in run_loop.calls)
    (tick,) = events(tmp_path, "watch_tick")
    assert {k: tick[k] for k in ("cycle", "new_matches", "kev_source", "next_in_s")} == {
        "cycle": 1, "new_matches": 2, "kev_source": "staged-only", "next_in_s": 0}
    triggers = events(tmp_path, "watch_trigger")
    assert [(t["cve"], t["package"], t["version"], t["run_id"]) for t in triggers] == [
        (m["cve"], m["package"], m["version"], i) for m, i in zip((YAML, JINJA), ids, strict=True)]


def test_second_cycle_with_the_same_scan_triggers_nothing(tmp_path):
    first, second = recorder(), recorder()
    once(tmp_path, scan_of(YAML, NOISE), first)
    stats = once(tmp_path, scan_of(YAML, NOISE), second)  # a restart: state comes from disk
    assert stats["triggered"] == 0 and not second.calls
    assert [t["new_matches"] for t in events(tmp_path, "watch_tick")] == [1, 0]
    assert state(tmp_path) == {"cycle": 2,
                               "seen": {"CVE-2020-14343|PyYAML|5.3.1": first.calls[0]["run_id"]}}


def test_a_new_kev_entry_later_triggers_only_that_one(tmp_path):
    run_loop = recorder()
    once(tmp_path, scan_of(YAML), run_loop)
    once(tmp_path, scan_of(YAML, JINJA), run_loop)
    assert [c["run_id"].rsplit("-", 1)[0] for c in run_loop.calls] == [
        "watch-CVE-2020-14343", "watch-CVE-2024-0001"]


def test_continuous_mode_sleeps_between_cycles_and_ctrl_c_stops_cleanly(tmp_path):
    naps = []

    def sleep(seconds):
        naps.append(seconds)
        if len(naps) == 2:
            raise KeyboardInterrupt

    run_loop = recorder()
    stats = watch.watch(interval=60, scan=scan_of(YAML), run_loop=run_loop, root=tmp_path,
                        sleep=sleep, live=False)
    assert stats == {"cycles": 2, "triggered": 1, "errors": 0, "stopped": True}
    assert naps == [60, 60] and len(run_loop.calls) == 1
    assert [t["next_in_s"] for t in events(tmp_path, "watch_tick")] == [60, 60]


def test_a_failed_run_is_journaled_and_the_daemon_continues(tmp_path):
    stats = once(tmp_path, scan_of(YAML, JINJA), recorder(fail=["CVE-2020-14343"]))
    assert stats == {"cycles": 1, "triggered": 2, "errors": 1, "stopped": False}
    (err,) = events(tmp_path, "watch_error")
    assert err["cve"] == "CVE-2020-14343" and err["error"] == "RuntimeError: twin unreachable"
    assert list(state(tmp_path)["seen"]) == ["CVE-2024-0001|Jinja2|2.10"]

    retry = recorder()
    once(tmp_path, scan_of(YAML, JINJA), retry)  # only the failed match runs again
    assert [c["run_id"].rsplit("-", 1)[0] for c in retry.calls] == ["watch-CVE-2020-14343"]
    assert len(state(tmp_path)["seen"]) == 2


def test_a_scan_that_raises_is_journaled_and_the_next_cycle_runs(tmp_path):
    def broken():
        raise OSError("feed down")

    assert once(tmp_path, broken, recorder())["errors"] == 1
    assert events(tmp_path, "watch_error")[0]["error"] == "OSError: feed down"
    assert not events(tmp_path, "watch_tick")
    assert once(tmp_path, scan_of(YAML), recorder())["triggered"] == 1
    assert state(tmp_path)["cycle"] == 2


def test_same_cve_in_two_packages_keeps_both_runs(tmp_path):
    run_loop = recorder()
    once(tmp_path, scan_of(YAML, {**YAML, "package": "ruamel"}), run_loop)
    ids = [c["run_id"] for c in run_loop.calls]
    assert len(set(ids)) == 2 and ids[1].endswith("-ruamel")


def test_main_passes_flags_and_prints_a_one_line_summary(monkeypatch, capsys):
    monkeypatch.setattr(config, "RED_SWARM", ["m-a"])
    seen = []

    def fake(**kw):
        seen.append(kw)
        return {"cycles": 3, "triggered": 1, "errors": 0, "stopped": True}

    monkeypatch.setattr(watch, "watch", fake)
    assert watch.main(["--once", "--local", "--interval", "60"]) == 0
    assert watch.main([]) == 0
    assert seen == [{"interval": 60, "once": True, "repo": None},
                    {"interval": watch.INTERVAL, "once": False, "repo": config.GITHUB_REPO}]
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert last.startswith("neo watch: stopped after 3 cycle(s), 1 run(s) triggered, 0 error(s)")


def test_main_without_a_swarm_fails_with_one_clear_message(monkeypatch):
    monkeypatch.setattr(config, "RED_SWARM", [])
    with pytest.raises(SystemExit) as e:
        watch.main(["--once"])
    assert "NEO_RED_SWARM" in str(e.value.code)
