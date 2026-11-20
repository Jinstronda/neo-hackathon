"""NEO loop CLI:  python -m neo [run_id] [--repo owner/name] [--no-screenshots]

Runs the whole closed loop once and prints where the artifact and the PR landed.
"""
import argparse
import sys

from . import orchestrator


def main(argv=None):
    p = argparse.ArgumentParser(prog="neo", description="run the NEO closed loop once")
    p.add_argument("run_id", nargs="?", default="demo-run")
    p.add_argument("--repo", default="Jinstronda/neo-hackathon")
    p.add_argument("--no-screenshots", action="store_true")
    args = p.parse_args(argv)

    s = orchestrator.loop(args.run_id, repo=args.repo, screenshots=not args.no_screenshots)

    pr = s["pr"]
    print(f"\nrun     runs/{s['id']}/run.json")
    print(f"pr      {pr['url']}  (patch_source={pr['patch_source']})")
    print(f"review  passed={s['review']['passed']}  comments={s['review']['comment_urls']}")
    print(f"retest  post_patch_green={s['retest']['post_patch_green']}  tests={s['retest']['tests']}")
    print(f"merge   ready={s['merge']['ready']}  awaiting={s['merge']['awaiting']}  "
          f"(a human merges on GitHub)")
    print(f"metrics {s['metrics']['minutes_exploit_to_fix']} min exploit->fix, "
          f"cost~${s['metrics']['cost_usd']}, {s['metrics']['regression_tests']} regression tests")
    return 0 if s["merge"]["ready"] else 2


if __name__ == "__main__":
    sys.exit(main())
