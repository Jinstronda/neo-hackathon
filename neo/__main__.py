"""The neo command: the loop, the 24/7 watch, the terminal agent and the tools
underneath, behind one entry point. `python -m neo demo-run` still runs the loop.

Every subcommand but run forwards its argv untouched to that module's own
main(argv), imported only when called, so one broken module never takes down
the others.
"""
import argparse
import importlib
import sys

from . import config

FORWARD = {
    "watch": ("neo.watch", "24/7: rescan the KEV feed, run the loop on every new match"),
    "chat": ("neo.chat", 'talk to Neo in the terminal ("Neo, attack our server")'),
    "radar": ("neo.radar", "SBOM x KEV x EPSS x OSV: what dropped, and are we exposed"),
    "harness": ("neo.harness.runner", "attack one scenario on a disposable target"),
    "replay": ("infra.replay", "rebuild a twin and replay every exploit (the retest gate)"),
    "term": ("neo.term", "print a recorded run in the terminal"),
}
MAX_SWARM = 5

EXAMPLES = """examples:
  neo                               run the loop once (same as: neo run)
  neo run --local --ask             ask before fixing; record the PR locally, no GitHub
  neo run --swarm 5                 widen the red swarm to five models
  neo watch --once --local          one 24/7 cycle, for cron or CI
  neo chat                          "Neo, attack our server"
  neo term replay runs/demo-run --slow
"""


def _swarm_size(s: str) -> int:
    n = int(s)
    if not 1 <= n <= MAX_SWARM:
        raise argparse.ArgumentTypeError(f"must be 1..{MAX_SWARM}")
    return n


def _positive(s: str) -> int:
    n = int(s)
    if n < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return n


def _add_run(sub) -> None:
    r = sub.add_parser("run", help="run the closed loop once: radar, red, blue, review, "
                                   "retest, merge gate")
    r.add_argument("run_id", nargs="?", default="demo-run",
                   help="names runs/<run_id>/ (default: %(default)s)")
    where = r.add_mutually_exclusive_group()
    where.add_argument("--repo", default=config.GITHUB_REPO, metavar="OWNER/NAME",
                       help="GitHub repo the fix PR opens on (default: %(default)s, "
                            "from $NEO_REPO)")
    where.add_argument("--local", action="store_true",
                       help="record the PR locally and never touch GitHub")
    r.add_argument("--ask", action="store_true",
                   help="after the swarm proves an exploit, ask before blue fixes it")
    r.add_argument("--swarm", type=_swarm_size, metavar="N",
                   help=f"red models in the swarm, 1..{MAX_SWARM} (default: all of "
                        "NEO_RED_SWARM)")
    r.add_argument("--max-fix-attempts", type=_positive, default=3, metavar="N",
                   help="blue tries, each verified on a fresh copy (default: %(default)s)")
    r.add_argument("--no-screenshots", action="store_true", help="skip the step screenshots")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="neo", epilog=EXAMPLES, formatter_class=argparse.RawDescriptionHelpFormatter,
        description="NEO: an AI red and blue team that proves every exploit and every\n"
                    "fix on a disposable twin before a human merges.")
    sub = p.add_subparsers(dest="cmd", metavar="command")
    _add_run(sub)
    for name, (_, help_) in FORWARD.items():
        sub.add_parser(name, help=help_, add_help=False)
    return p


def confirm_fix(findings: list[dict], ask=None) -> bool:
    """--ask: show what the swarm proved, then a human decides whether blue runs."""
    ask = ask or input
    print(f"\nNEO proved {len(findings)} exploit(s) on the disposable twin:")
    for f in findings:
        print(f"  {f.get('cls') or f.get('class')} @ {f.get('location')}"
              f"  (confirmed by {f.get('confirmed_by')})")
    try:
        return ask("Fix it? [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:  # no terminal attached: the safe answer is no
        return False


def run(args: argparse.Namespace) -> int:
    try:
        models = config.swarm(args.swarm)
    except RuntimeError as e:
        raise SystemExit(f"neo: {e}") from None
    loop = importlib.import_module("neo.orchestrator").loop
    s = loop(args.run_id, repo=None if args.local else args.repo, models=models,
             screenshots=not args.no_screenshots, max_fix_attempts=args.max_fix_attempts,
             approve=confirm_fix if args.ask else None)
    print_summary(s)
    return 0 if s.get("merge", {}).get("ready") else 2


def print_summary(s: dict) -> None:
    pr, rv, rt, mt = (s.get(k) or {} for k in ("pr", "review", "retest", "metrics"))
    merge = s.get("merge") or {}
    print(f"\nrun     runs/{s['id']}/run.json")
    if pr:
        print(f"pr      {pr.get('url')}  (patch_source={pr.get('patch_source')})")
    if rv:
        print(f"review  passed={rv.get('passed')}  comments={rv.get('comment_urls')}")
    if rt:
        print(f"retest  post_patch_green={rt.get('post_patch_green')}  tests={rt.get('tests')}")
    print(f"merge   ready={merge.get('ready', False)}  awaiting={merge.get('awaiting')}  "
          f"(a human presses merge)")
    if mt.get("minutes_exploit_to_fix") is not None:  # a halted run never reached a fix
        print(f"metrics {mt.get('minutes_exploit_to_fix')} min exploit->fix, "
              f"cost~${mt.get('cost_usd')}, {mt.get('regression_tests')} regression tests")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in FORWARD:
        return importlib.import_module(FORWARD[argv[0]][0]).main(argv[1:]) or 0
    if not argv or argv[0] not in ("run", "-h", "--help"):
        argv.insert(0, "run")  # back-compat: python -m neo [run_id] [flags]
    return run(parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
