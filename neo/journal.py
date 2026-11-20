"""The run journal. Every step of the loop appends one JSON event. The UI
reads these events to draw the board, the timeline and the numbers. Server-side
flag checks, not agent claims, decide red/green."""
import json
import time
from pathlib import Path


class Journal:
    def __init__(self, run_dir, clock=time.time):
        self.dir = Path(run_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "events.jsonl"
        self._clock = clock
        self.events = []

    def emit(self, type, **fields):
        ev = {"type": type, "ts": round(self._clock(), 3), **fields}
        self.events.append(ev)
        with self.path.open("a") as f:
            f.write(json.dumps(ev) + "\n")
        return ev

    def write_summary(self, summary):
        (self.dir / "run.json").write_text(json.dumps(summary, indent=2))


# Event vocabulary (the contract the web UI and neo.term read), in loop order:
#   radar_match    {cve, kev, epss, osv, package, version, reachable, kev_source}
#   twin_create    {twin_id, where:"server"|"local", image}
#   red_start      {twin_id, models:[...]}   # shown as "model-1".."model-n" in public UI
#   red_finding    {finding_id, model, cls, location, request, response, confirmed_by, found_by}
#   flag_check     {finding_id, scenario, phase:"pre-patch"|"post-patch", objective_complete,
#                   evidence:[...]}
#   fix_approval   {approved:bool, by:"human"|"auto"}   # recorded before blue touches anything
#   fix_attempt    {attempt, of, source:"model"|"canonical", ok, exploits_dead:{scenario: bool},
#                   legit_login_ok, error?}   # one per fixer try; a failed verify loops back
#   blue_patch     {finding_id, pr_url, pr_number, branch, diff, digest, commits:[{msg, kind}]}
#   review         {pr_number, reviewer:"security"|"correctness", vendor,
#                   verdict:"approve"|"request_changes", comment, rechecked:true,
#                   recheck_evidence:{...}}
#   review_disagreement {pr_number, pr_digest, resolution:"human", columns:[...]}
#                   # reviewers split; a human decides
#   twin_deploy    {twin_id, where, image, finding_id, phase}
#   twin_fallback  {reason, detail, phase}   # Docker unavailable; a process twin replays
#   exploit_run    {exploit, exit, tail}     # evidence only; the flag check decides
#   retest         {finding_id, scenario, objective_complete, status:"green"|"red", phase}
#   retest_summary {phase, status, gate_pass}
#   tests          {passed, total, regression_added, ok}
#   merge_ready    {pr_number, ready, blockers:[...], approved_by:[...], awaiting:"human"}
#                   # gate passed; a human merges
#   merge          {pr_number, by:"human", approved_by:[...]}
#   release        {pr_number, digest, regression}
#                   # after a human merges: the fixed bug becomes a permanent CI regression
#   metrics        {minutes_exploit_to_fix, cost_usd, where:"EU", tested_surface,
#                   untested_surface, regression_tests}
#   watch_tick     {cycle, new_matches, kev_source, next_in_s}   # 24/7 mode: one radar poll
#   watch_trigger  {cve, package, version, run_id}               # a new match starts a run
