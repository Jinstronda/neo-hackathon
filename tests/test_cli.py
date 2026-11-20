"""The neo CLI: every subcommand reaches its target with its argv intact, the old
`python -m neo [run_id]` form still runs the loop, and --local, --swarm, --ask and
--max-fix-attempts reach orchestrator.loop. Every target is a fake; nothing real runs."""
import os
import sys
import types
from pathlib import Path

import pytest

from neo import __main__ as cli
from neo import config, env

FINDINGS = [{"cls": "SQL injection", "location": "POST /login",
             "confirmed_by": "server-side flag check"}]


@pytest.fixture
def swarm(monkeypatch):
    monkeypatch.setattr(config, "RED_SWARM", ["m-a", "m-b", "m-c"])
    monkeypatch.setattr(config, "RED_SWARM_EXTRA", ["m-d", "m-e"])


def fake_loop(monkeypatch, merge=None, **extra):
    calls = []

    def loop(run_id, **kw):
        calls.append({"run_id": run_id, **kw})
        if kw.get("approve"):
            calls[-1]["approved"] = kw["approve"](FINDINGS)
        return {"id": run_id, "merge": merge or {"ready": True, "awaiting": "human"}, **extra}

    monkeypatch.setitem(sys.modules, "neo.orchestrator", types.SimpleNamespace(loop=loop))
    return calls


@pytest.fixture
def loop(monkeypatch, swarm):
    return fake_loop(monkeypatch)


def test_help_lists_every_command(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--help"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    for cmd in ["run", *cli.FORWARD]:
        assert f"    {cmd} " in out


@pytest.mark.parametrize("argv, run_id", [
    ([], "demo-run"), (["run"], "demo-run"), (["demo-run"], "demo-run"),
    (["my-run"], "my-run"), (["run", "my-run"], "my-run"), (["--no-screenshots"], "demo-run")])
def test_run_routes_and_keeps_the_old_positional_form(loop, argv, run_id):
    assert cli.main(argv) == 0
    call = loop[-1]
    assert call["run_id"] == run_id
    assert call["repo"] == config.GITHUB_REPO
    assert call["models"] == ["m-a", "m-b", "m-c"]
    assert call["approve"] is None and call["max_fix_attempts"] == 3


def test_local_means_no_repo(loop):
    cli.main(["run", "--local"])
    assert loop[-1]["repo"] is None


def test_flags_reach_the_loop(loop):
    cli.main(["run", "r1", "--repo", "acme/api", "--max-fix-attempts", "5", "--no-screenshots"])
    call = loop[-1]
    assert (call["repo"], call["max_fix_attempts"], call["screenshots"]) == ("acme/api", 5, False)


def test_repo_and_local_are_exclusive(loop):
    with pytest.raises(SystemExit) as e:
        cli.main(["run", "--repo", "acme/api", "--local"])
    assert e.value.code == 2 and not loop


@pytest.mark.parametrize("n, models", [
    ("1", ["m-a"]), ("3", ["m-a", "m-b", "m-c"]), ("5", ["m-a", "m-b", "m-c", "m-d", "m-e"])])
def test_swarm_takes_the_first_n(loop, n, models):
    cli.main(["run", "--swarm", n])
    assert loop[-1]["models"] == models


@pytest.mark.parametrize("n", ["0", "6", "many"])
def test_swarm_size_is_bounded(loop, n):
    with pytest.raises(SystemExit) as e:
        cli.main(["run", "--swarm", n])
    assert e.value.code == 2 and not loop


def test_empty_swarm_fails_with_one_clear_message(monkeypatch, loop):
    monkeypatch.setattr(config, "RED_SWARM", [])
    with pytest.raises(SystemExit) as e:
        cli.main(["run", "--local"])
    assert "NEO_RED_SWARM" in str(e.value.code) and not loop


@pytest.mark.parametrize("answer, approved", [("y", True), (" YES ", True), ("n", False),
                                              ("", False)])
def test_ask_lists_the_findings_and_waits_for_a_human(loop, monkeypatch, capsys, answer,
                                                       approved):
    prompts = []
    monkeypatch.setattr("builtins.input", lambda p: prompts.append(p) or answer)
    cli.main(["run", "--ask", "--local"])
    assert loop[-1]["approved"] is approved
    assert prompts == ["Fix it? [y/N] "]
    out = capsys.readouterr().out
    assert "SQL injection @ POST /login  (confirmed by server-side flag check)" in out


def test_ask_without_a_terminal_means_no():
    def eof(_prompt):
        raise EOFError
    assert cli.confirm_fix(FINDINGS, ask=eof) is False


def test_declined_fix_prints_and_exits_not_ready(monkeypatch, swarm, capsys):
    fake_loop(monkeypatch, merge={"ready": False, "awaiting": "fix approval"},
              metrics={"minutes_exploit_to_fix": None, "regression_tests": 0})
    monkeypatch.setattr("builtins.input", lambda p: "n")
    assert cli.main(["run", "r2", "--ask", "--local"]) == 2
    out = capsys.readouterr().out
    assert "runs/r2/run.json" in out and "awaiting=fix approval" in out
    assert "metrics" not in out


def test_full_summary_prints_every_line(monkeypatch, swarm, capsys):
    fake_loop(monkeypatch,
              pr={"url": "runs/r3/pr.json", "patch_source": "model"},
              review={"passed": True, "comment_urls": []},
              retest={"post_patch_green": True, "tests": "10/10"},
              metrics={"minutes_exploit_to_fix": 1.5, "cost_usd": 0.01, "regression_tests": 3})
    assert cli.main(["run", "r3", "--local"]) == 0
    out = capsys.readouterr().out
    for head in ("run ", "pr ", "review ", "retest ", "merge ", "metrics "):
        assert f"\n{head}" in out


@pytest.mark.parametrize("cmd", list(cli.FORWARD))
def test_passthrough_forwards_argv_untouched(monkeypatch, cmd):
    seen = []
    mod = types.SimpleNamespace(main=lambda argv=None: seen.append(argv) or 7)
    monkeypatch.setitem(sys.modules, cli.FORWARD[cmd][0], mod)
    rest = ["replay", "runs/demo-run", "--slow", "0.1", "--help", "-x"]
    assert cli.main([cmd, *rest]) == 7
    assert seen == [rest]


def test_passthrough_none_means_success(monkeypatch):
    monkeypatch.setitem(sys.modules, "neo.radar", types.SimpleNamespace(main=lambda a: None))
    assert cli.main(["radar"]) == 0


def test_swarm_ids_parse_from_a_comma_list(monkeypatch):
    monkeypatch.setenv("NEO_RED_SWARM", " p/a, p/b ,,p/c ")
    assert config._ids("NEO_RED_SWARM") == ["p/a", "p/b", "p/c"]


def test_config_source_names_no_red_model():
    source = Path(config.__file__).read_text()
    assert all(m not in source for m in config.RED_SWARM + config.RED_SWARM_EXTRA)


def test_env_loader_unquotes_and_never_overrides(tmp_path, monkeypatch):
    for k in ("NEO_T_A", "NEO_T_B", "NEO_T_C"):
        monkeypatch.setenv(k, "")
        monkeypatch.delenv(k)  # restored to absent after the test
    monkeypatch.setenv("NEO_T_C", "mine")
    f = tmp_path / ".env"
    f.write_text("# comment\nexport NEO_T_A=\"p/a,p/b\"\nNEO_T_B='x'\nNEO_T_C=theirs\n\nnoise\n")
    env.load(f)
    assert (os.environ["NEO_T_A"], os.environ["NEO_T_B"], os.environ["NEO_T_C"]) == (
        "p/a,p/b", "x", "mine")
