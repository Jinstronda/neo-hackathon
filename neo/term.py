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
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from .journal import Journal

COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
CODES = {"red": "31", "grn": "32", "yel": "33", "blu": "34", "mag": "35", "cyn": "36",
         "dim": "2", "b": "1"}
ANSI = re.compile(r"\x1b\[[0-9;]*m")
# strips C0/C1 control bytes (escape sequences included) from event-derived text before it
# ever reaches a real terminal; exploit output and model-written text are untrusted data
CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
WIDTH = 96

# event type -> loop step (same order as orchestrator.STEPS)
STEP_OF = {
    "radar_match": ("1", "Radar match", "SBOM x KEV x EPSS x OSV"),
    "twin_create": ("2", "NEO proves the exploit", "disposable twins, server-side flag checks"),
    "red_start": ("2", "NEO proves the exploit", "disposable twins, server-side flag checks"),
    "fix_attempt": ("3", "Blue opens the patch PR", "fix written, real PR opened"),
    "blue_patch": ("3", "Blue opens the patch PR", "fix written, real PR opened"),
    "review": ("4", "Two reviewers check the PR", "two vendors, each re-runs its claim"),
    "twin_deploy": ("5", "Twin rebuilt, exploit replayed", "same exploits, before and after"),
    "merge_ready": ("6", "Human merges", "the loop stops at a merge a human presses"),
}


def c(color: str, s) -> str:
    """Wrap s in an ANSI color, or return it plain when color is off."""
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
    return textwrap.shorten(" ".join(CTRL.sub("?", str(s)).split()), n, placeholder=" ...")


def _plain(*parts, n=40):
    """Event-derived values, each sanitized and shortened, two spaces apart."""
    return "  ".join(_short(p, n) for p in parts)


def _diffstat(diff):
    lines = (diff or "").splitlines()
    files = sum(ln.startswith("diff --git") for ln in lines)
    add = sum(ln.startswith("+") and not ln.startswith("+++") for ln in lines)
    rem = sum(ln.startswith("-") and not ln.startswith("---") for ln in lines)
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

    def banner(self, num: str, title: str, sub: str) -> None:
        rule = "=" * max(3, WIDTH - 14 - len(title))
        self._w()
        self._w(c("b", f"== STEP {num}  {title.upper()} ") + c("dim", rule))
        self._w(c("dim", f"   {sub}"))

    def event(self, ev: dict) -> None:
        """Print one journal event, with a step banner when the loop moves on."""
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
                   f"KEV {_yes(e.get('kev'))}   EPSS {e.get('epss')}   "
                   f"reachable {_yes(e.get('reachable'))}",
                   c("dim", f"OSV {', '.join(e.get('osv') or [])}   "
                            f"KEV source {e.get('kev_source')}"),
                   c("dim", "a CVE is a worklist item, not a finding; "
                            "proof comes next, on the twin"))

    def _twin_create(self, e):
        self._line(e["ts"], "twin", "cyn",
                   f"{e.get('twin_id')}  ({e.get('where')}, {e.get('image')})")

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
        evidence = e.get("evidence")
        more = [c("dim", _short(f"evidence: {_kv(evidence)}"))] if evidence else []
        self._line(e["ts"], "flag", "red" if done else "grn",
                   f"{e.get('scenario')}  {e.get('phase')}  objective_complete="
                   f"{c('red', 'true') if done else c('grn', 'false')}", *more)

    def _fix_approval(self, e):
        ok = e.get("approved") is True
        verdict = c("grn", "approved") if ok else c("yel", "not approved")
        more = [] if ok else [c("dim", "blue does not run; the proven findings wait for a human")]
        self._line(e["ts"], "approve", "grn" if ok else "yel",
                   f"fix {verdict} by {_short(e.get('by'), 20)}", *more)

    def _fix_attempt(self, e):
        ok = e.get("ok") is True
        dead = e.get("exploits_dead") or {}
        replayed = ", ".join(f"{s} {'dead' if d else 'ALIVE'}" for s, d in dead.items())
        login = c("dim", "still works") if e.get("legit_login_ok") else c("red", "BROKEN")
        more = [c("dim", _short(f"fresh copy: {replayed or 'no exploit replayed'}")),
                c("dim", "legit login ") + login]
        more += [c("yel", _short(f"error: {e['error']}"))] if e.get("error") else []
        self._line(e["ts"], "fix", "grn" if ok else "red",
                   _plain(f"attempt {e.get('attempt')}/{e.get('of')}",
                          f"{e.get('source')} patch")
                   + "  " + (c("grn", "verified") if ok else c("red", "rejected")), *more)

    def _blue_patch(self, e):
        files, add, rem = _diffstat(e.get("diff"))
        msgs = [m.get("msg", "") for m in e.get("commits") or []]
        self._line(e["ts"], "patch", "blu",
                   f"PR #{e.get('pr_number')}  {c('b', e.get('pr_url'))}",
                   f"branch {e.get('branch')}  ·  {files} files, "
                   f"{c('grn', f'+{add}')} {c('red', f'-{rem}')}"
                   f"  ·  digest {str(e.get('digest'))[:12]}",
                   *[c("dim", _short(f"commit: {m}")) for m in msgs])

    def _review(self, e):
        ok = e.get("verdict") == "approve"
        ev = e.get("recheck_evidence") or {}
        self._line(e["ts"], "review", "grn" if ok else "yel",
                   f"{e.get('reviewer')} ({e.get('vendor')})  "
                   f"{c('grn' if ok else 'yel', str(e.get('verdict')).upper())}"
                   f"   rechecked={e.get('rechecked')}"
                   f"  exploit_still_works={ev.get('exploit_still_works')}",
                   c("dim", _short(e.get("comment", ""))))

    def _review_disagreement(self, e):
        self._line(e["ts"], "split", "yel",
                   f"reviewers disagree on digest {str(e.get('pr_digest'))[:12]}"
                   f"  ->  resolution: {c('b', e.get('resolution'))}")

    def _twin_deploy(self, e):
        self._line(e["ts"], "twin", "cyn",
                   f"{c('b', e.get('phase'))}  {e.get('twin_id')}  "
                   f"({e.get('where')}, {e.get('image')})")

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

    def _watch_tick(self, e):
        n = e.get("new_matches") or 0
        self._line(e["ts"], "watch", "yel" if n else "dim",
                   _plain(f"cycle {e.get('cycle')}", f"{n} new KEV matches in the SBOM",
                          f"KEV {e.get('kev_source')}", f"next check in {e.get('next_in_s')}s"))

    def _watch_trigger(self, e):
        self._line(e["ts"], "trigger", "red",
                   f"{c('b', _short(e.get('cve'), 30))}  "
                   + _plain(f"{e.get('package')} {e.get('version')}",
                            f"-> run {e.get('run_id')}"),
                   c("dim", "a new KEV entry matches the SBOM; the loop starts on its own"))

    def _watch_error(self, e):
        run = e.get("run_id")
        where = f"run {run} ({e.get('cve')})" if run else f"cycle {e.get('cycle')}"
        self._line(e["ts"], "watch", "red", _plain(where, f"error: {e.get('error')}", n=80),
                   c("dim", "journaled; the daemon keeps going and the next cycle retries"))

    def _generic(self, e):
        rest = " ".join(f"{k}={v}" for k, v in e.items() if k not in ("type", "ts"))
        self._line(e.get("ts"), e["type"][:8], "dim", _short(rest))

    def summary(self) -> None:
        """The closing box. A row prints only when its events are in the journal."""
        by = {}
        for ev in self.seen:
            by.setdefault(ev["type"], []).append(ev)

        def last(t):
            return (by.get(t) or [{}])[-1]

        radar, pr, tests, gate, m = (last(t) for t in ("radar_match", "blue_patch", "tests",
                                                        "merge_ready", "metrics"))
        fix, approval = last("fix_attempt"), last("fix_approval")
        found = by.get("red_finding", [])
        post = [r for r in by.get("retest", []) if r.get("phase") == "post-patch"]
        green = sum(r.get("status") == "green" for r in post)
        when = datetime.datetime.fromtimestamp(self.t0 or 0, datetime.UTC)
        fixed = c("grn", "verified") if fix.get("ok") else c("red", "failed")
        dead = c("grn" if post and green == len(post) else "red", f"{green}/{len(post)}")
        blockers = gate.get("blockers")
        blocked = c("yel", f"  ({'; '.join(blockers)})") if blockers else ""
        rows = [
            (True, c("b", f"NEO run {self.run_id}".strip())
                   + c("dim", f"   {when:%Y-%m-%d %H:%M} UTC")),
            (True, ""),
            ("radar_match" in by,
             f"matched     {radar.get('cve')} in {radar.get('package')} {radar.get('version')}"),
            ("red_start" in by or bool(found),
             f"proven      {c('red', len(found))} exploits: "
             f"{', '.join(f.get('cls', '?') for f in found)}"),
            (approval.get("approved") is False,
             f"fix         {c('yel', 'not approved')}; blue did not run"),
            ("fix_attempt" in by,
             f"fix         attempt {fix.get('attempt')}/{fix.get('of')} {fixed}"
             f" ({_short(fix.get('source'), 20)} patch)"),
            ("blue_patch" in by, f"patch       PR #{pr.get('pr_number')}  {pr.get('pr_url')}"),
            ("review" in by, "reviews     " + "   ".join(
                f"{r.get('reviewer')}/{r.get('vendor')} "
                f"{c('grn' if r.get('verdict') == 'approve' else 'yel', r.get('verdict'))}"
                for r in by.get("review", []))),
            (bool(post),
             f"replay      {dead} exploits dead on the patched twin"),
            ("tests" in by, f"tests       {tests.get('passed')}/{tests.get('total')} passed"),
            ("merge_ready" in by,
             f"merge       ready={c('grn' if gate.get('ready') else 'yel', gate.get('ready'))}"
             f"  awaiting {gate.get('awaiting')}{blocked}"),
            ("metrics" in by,
             f"time/cost   {m.get('minutes_exploit_to_fix')} min exploit->fix"
             f"  ·  ${m.get('cost_usd')}  ·  {m.get('where')}"),
        ]
        rows = [text for shown, text in rows if shown]
        w = max(_vlen(r) for r in rows) + 2
        self._w()
        self._w(c("dim", "┌" + "─" * w + "┐"))
        for r in rows:
            self._w(c("dim", "│ ") + r + " " * (w - 1 - _vlen(r)) + c("dim", "│"))
        self._w(c("dim", "└" + "─" * w + "┘"))


def attach(journal: "Journal", out: TextIO = sys.stdout) -> Printer:
    """Print every event the journal emits, live."""
    p = Printer(out, run_id=journal.dir.name)
    emit = journal.emit

    def emit_and_print(type, **fields):
        ev = emit(type, **fields)
        p.event(ev)
        return ev

    journal.emit = emit_and_print
    return p


def replay(run_dir: str | Path, delay: float = 0.0, out: TextIO = sys.stdout) -> Printer:
    """Re-print a finished run from its events.jsonl, then the summary box."""
    run_dir = Path(run_dir)
    p = Printer(out, delay, run_dir.name)
    p._w(c("b", "NEO") + c("dim", f"  replaying {run_dir}/events.jsonl"))
    for line in (run_dir / "events.jsonl").read_text().splitlines():
        if line.strip():
            p.event(json.loads(line))
    if not any(e["type"] == "metrics" for e in p.seen):
        p.summary()
    return p


def main(argv: list[str] | None = None) -> int:
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
