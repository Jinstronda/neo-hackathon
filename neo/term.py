"""Terminal view of a NEO run. Prints each journal event as one narrated line,
a banner when the loop enters a new step, and a summary box at the end.

  live:    the orchestrator calls attach(journal), so `python -m neo` prints as it runs
  replay:  python -m neo.term replay runs/demo-run [--slow [SECONDS]]

It only formats what is in events.jsonl; it never adds a number or a finding.
Colors follow NO_COLOR and turn off when stdout is not a terminal.
"""
import argparse
import datetime
import json
import os
import re
import sys
import textwrap
import time
from pathlib import Path

COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
CODES = {"red": "31", "grn": "32", "yel": "33", "blu": "34", "mag": "35", "cyn": "36",
         "dim": "2", "b": "1"}
ANSI = re.compile(r"\x1b\[[0-9;]*m")
WIDTH = 96

# event type -> loop step (same order as orchestrator.STEPS)
STEP_OF = {
    "radar_match": ("1", "Radar match", "SBOM x KEV x EPSS x OSV"),
    "twin_create": ("2", "NEO proves the exploit", "disposable twins, server-side flag checks"),
    "red_start": ("2", "NEO proves the exploit", "disposable twins, server-side flag checks"),
    "blue_patch": ("3", "Blue opens the patch PR", "fix written, real PR opened"),
    "review": ("4", "Two reviewers check the PR", "two vendors, each re-runs its claim"),
    "twin_deploy": ("5", "Twin rebuilt, exploit replayed", "same exploits, before and after"),
    "merge_ready": ("6", "Human merges", "the loop stops at a merge a human presses"),
}


def c(color, s):
    return f"\x1b[{CODES[color]}m{s}\x1b[0m" if COLOR else str(s)


def _vlen(s):
    return len(ANSI.sub("", s))


def _yes(v):
    return c("red", "yes") if v else c("dim", "no")


def _kv(items):
    """[{type, k: v}] -> 'type k=v, type k=v'"""
    out = []
    for e in items or []:
        rest = " ".join(f"{k}={v}" for k, v in e.items() if k != "type")
        out.append(f"{e.get('type', '?')} {rest}".strip())
    return ", ".join(out)


def _short(s, n=WIDTH - 12):
    return textwrap.shorten(" ".join(str(s).split()), n, placeholder=" ...")


def _diffstat(diff):
    lines = (diff or "").splitlines()
    files = sum(l.startswith("diff --git") for l in lines)
    add = sum(l.startswith("+") and not l.startswith("+++") for l in lines)
    rem = sum(l.startswith("-") and not l.startswith("---") for l in lines)
    return files, add, rem


class Printer:
    def __init__(self, out=sys.stdout, delay=0.0, run_id=""):
        self.out, self.delay, self.run_id = out, delay, run_id
        self.t0 = None
        self.step = None
        self.seen = []

    def _line(self, ts, tag, color, text, *more):
        stamp = c("dim", self._clock(ts))
        self._w(f"{stamp}  {c(color, f'{tag:<8}')} {text}")
        for m in more:
            self._w(f"{'':7}  {'':8} {m}")

    def _w(self, s=""):
        print(s, file=self.out, flush=True)
        if self.delay:
            time.sleep(self.delay)

    def _clock(self, ts):
        s = int((ts or self.t0) - self.t0)
        return f"+{s // 60:02d}:{s % 60:02d}"

    def banner(self, num, title, sub):
        self._w()
        self._w(c("b", f"== STEP {num}  {title.upper()} ") + c("dim", "=" * max(3, WIDTH - 14 - len(title))))
        self._w(c("dim", f"   {sub}"))

    def event(self, ev):
        if self.t0 is None:
            self.t0 = ev.get("ts", 0)
        self.seen.append(ev)
        st = STEP_OF.get(ev["type"])
        if st and st[0] != self.step:
            self.step = st[0]
            self.banner(*st)
        getattr(self, "_" + ev["type"], self._generic)(ev)

    def _radar_match(self, e):
        self._line(e["ts"], "radar", "yel",
                   f"{c('b', e.get('cve'))}  {e.get('package')} {e.get('version')}   "
                   f"KEV {_yes(e.get('kev'))}   EPSS {e.get('epss')}   reachable {_yes(e.get('reachable'))}",
                   c("dim", f"OSV {', '.join(e.get('osv') or [])}   KEV source {e.get('kev_source')}"),
                   c("dim", "a CVE is a worklist item, not a finding; proof comes next, on the twin"))

    def _twin_create(self, e):
        self._line(e["ts"], "twin", "cyn", f"{e.get('twin_id')}  ({e.get('where')}, {e.get('image')})")

    def _red_start(self, e):
        models = e.get("models") or []
        self._line(e["ts"], "swarm", "mag",
                   f"{len(models)} models attack twin {e.get('twin_id')}: {' '.join(models)}")

    def _red_finding(self, e):
        self._line(e["ts"], "[RED]", "red",
                   f"{c('b', e.get('finding_id'))} {e.get('cls')} @ {e.get('location')}",
                   c("dim", f"found by {', '.join(e.get('found_by') or [e.get('model')])}"
                            f"  ·  confirmed by {e.get('confirmed_by')}"),
                   c("dim", f"proof: {_short(_kv(e.get('response')))}"))

    def _flag_check(self, e):
        done = e.get("objective_complete")
        self._line(e["ts"], "flag", "red" if done else "grn",
                   f"{e.get('scenario')}  {e.get('phase')}  objective_complete="
                   f"{c('red', 'true') if done else c('grn', 'false')}",
                   *([c("dim", _short(f"evidence: {_kv(e.get('evidence'))}"))] if e.get("evidence") else []))

    def _blue_patch(self, e):
        files, add, rem = _diffstat(e.get("diff"))
        msgs = [m.get("msg", "") for m in e.get("commits") or []]
        self._line(e["ts"], "patch", "blu",
                   f"PR #{e.get('pr_number')}  {c('b', e.get('pr_url'))}",
                   f"branch {e.get('branch')}  ·  {files} files, {c('grn', f'+{add}')} {c('red', f'-{rem}')}"
                   f"  ·  digest {str(e.get('digest'))[:12]}",
                   *[c("dim", _short(f"commit: {m}")) for m in msgs])

    def _review(self, e):
        ok = e.get("verdict") == "approve"
        ev = e.get("recheck_evidence") or {}
        self._line(e["ts"], "review", "grn" if ok else "yel",
                   f"{e.get('reviewer')} ({e.get('vendor')})  "
                   f"{c('grn' if ok else 'yel', str(e.get('verdict')).upper())}"
                   f"   rechecked={e.get('rechecked')}  exploit_still_works={ev.get('exploit_still_works')}",
                   c("dim", _short(e.get("comment", ""))))

    def _review_disagreement(self, e):
        self._line(e["ts"], "split", "yel",
                   f"reviewers disagree on digest {str(e.get('pr_digest'))[:12]}  ->  "
                   f"resolution: {c('b', e.get('resolution'))}")

    def _twin_deploy(self, e):
        self._line(e["ts"], "twin", "cyn",
                   f"{c('b', e.get('phase'))}  {e.get('twin_id')}  ({e.get('where')}, {e.get('image')})")

    def _exploit_run(self, e):
        ok = e.get("exit") == 0
        self._line(e["ts"], "exploit", "red" if ok else "grn",
                   f"{e.get('exploit')}  exit={e.get('exit')}  "
                   + c("dim", _short(str(e.get("tail", "")).strip(), WIDTH - 40)))

    def _retest(self, e):
        green = e.get("status") == "green"
        self._line(e["ts"], "[GREEN]" if green else "[RED]", "grn" if green else "red",
                   f"retest {e.get('scenario')}  {e.get('phase')}  status={e.get('status')}")

    def _retest_summary(self, e):
        green = e.get("status") == "green"
        self._line(e["ts"], "gate", "grn" if green else "red",
                   f"{e.get('phase')} replay: {c('grn' if green else 'red', e.get('status'))}"
                   f"   gate_pass={e.get('gate_pass')}")

    def _tests(self, e):
        self._line(e["ts"], "tests", "grn" if e.get("ok") else "red",
                   f"{e.get('passed')}/{e.get('total')} passed   "
                   f"({e.get('regression_added')} regression tests added)")

    def _merge_ready(self, e):
        ready = e.get("ready")
        more = [c("dim", f"approved by {', '.join(e.get('approved_by') or []) or 'nobody'}")]
        more += [c("yel", f"blocker: {b}") for b in e.get("blockers") or []]
        more.append(c("dim", _short(f"rule: {e.get('rule')}")) if e.get("rule") else "")
        self._line(e["ts"], "merge", "grn" if ready else "yel",
                   f"PR #{e.get('pr_number')}  ready_to_merge={c('grn' if ready else 'yel', ready)}"
                   f"   awaiting {c('b', e.get('awaiting'))}", *[m for m in more if m])

    def _merge(self, e):
        self._line(e["ts"], "merge", "grn",
                   f"PR #{e.get('pr_number')} merged by {e.get('by')}  "
                   f"(approved by {', '.join(e.get('approved_by') or [])})")

    def _metrics(self, e):
        self._line(e["ts"], "metrics", "cyn",
                   f"{e.get('minutes_exploit_to_fix')} min exploit->fix  ·  ${e.get('cost_usd')}"
                   f"  ·  {e.get('where')}  ·  surface tested {e.get('tested_surface')}"
                   f" / untested {e.get('untested_surface')}")
        self.summary()

    def _generic(self, e):
        rest = " ".join(f"{k}={v}" for k, v in e.items() if k not in ("type", "ts"))
        self._line(e.get("ts"), e["type"][:8], "dim", _short(rest))

    def summary(self):
        by = {}
        for ev in self.seen:
            by.setdefault(ev["type"], []).append(ev)
        last = lambda t: (by.get(t) or [{}])[-1]
        radar, pr, tests, gate, m = (last(t) for t in ("radar_match", "blue_patch", "tests",
                                                        "merge_ready", "metrics"))
        found = by.get("red_finding", [])
        post = [r for r in by.get("retest", []) if r.get("phase") == "post-patch"]
        green = sum(r.get("status") == "green" for r in post)
        when = datetime.datetime.fromtimestamp(self.t0 or 0, datetime.timezone.utc)
        rows = [
            c("b", f"NEO run {self.run_id}".strip()) + c("dim", f"   {when:%Y-%m-%d %H:%M} UTC"),
            "",
            f"matched     {radar.get('cve')} in {radar.get('package')} {radar.get('version')}",
            f"proven      {c('red', len(found))} exploits: {', '.join(f.get('cls', '?') for f in found)}",
            f"patch       PR #{pr.get('pr_number')}  {pr.get('pr_url')}",
            "reviews     " + "   ".join(
                f"{r.get('reviewer')}/{r.get('vendor')} "
                f"{c('grn' if r.get('verdict') == 'approve' else 'yel', r.get('verdict'))}"
                for r in by.get("review", [])),
            f"replay      {c('grn' if post and green == len(post) else 'red', f'{green}/{len(post)}')}"
            f" exploits dead on the patched twin",
            f"tests       {tests.get('passed')}/{tests.get('total')} passed",
            f"merge       ready={c('grn' if gate.get('ready') else 'yel', gate.get('ready'))}"
            f"  awaiting {gate.get('awaiting')}"
            + (c("yel", f"  ({'; '.join(gate.get('blockers'))})") if gate.get("blockers") else ""),
            f"time/cost   {m.get('minutes_exploit_to_fix')} min exploit->fix  ·  ${m.get('cost_usd')}"
            f"  ·  {m.get('where')}",
        ]
        w = max(_vlen(r) for r in rows) + 2
        self._w()
        self._w(c("dim", "┌" + "─" * w + "┐"))
        for r in rows:
            self._w(c("dim", "│ ") + r + " " * (w - 1 - _vlen(r)) + c("dim", "│"))
        self._w(c("dim", "└" + "─" * w + "┘"))


def attach(journal, out=sys.stdout):
    """Print every event the journal emits, live."""
    p = Printer(out, run_id=journal.dir.name)
    emit = journal.emit

    def emit_and_print(type, **fields):
        ev = emit(type, **fields)
        p.event(ev)
        return ev

    journal.emit = emit_and_print
    return p


def replay(run_dir, delay=0.0, out=sys.stdout):
    run_dir = Path(run_dir)
    p = Printer(out, delay, run_dir.name)
    p._w(c("b", "NEO") + c("dim", f"  replaying {run_dir}/events.jsonl"))
    for line in (run_dir / "events.jsonl").read_text().splitlines():
        if line.strip():
            p.event(json.loads(line))
    if not any(e["type"] == "metrics" for e in p.seen):
        p.summary()
    return p


def main(argv=None):
    ap = argparse.ArgumentParser(prog="neo.term", description="print a NEO run in the terminal")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("replay", help="re-print runs/<id>/events.jsonl")
    r.add_argument("run_dir")
    r.add_argument("--slow", nargs="?", type=float, const=0.35, default=0.0, metavar="SECONDS",
                   help="pause between lines (default 0.35s when given)")
    a = ap.parse_args(argv)
    replay(a.run_dir, a.slow)
    return 0


if __name__ == "__main__":
    sys.exit(main())
