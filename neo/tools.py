"""NEO's tool registry for the terminal agent. Each tool is a thin wrapper over
the orchestrator and the radar, and the schemas are the OpenAI-compatible tool
list the chat model sees. The human merge gate is not here: the REPL asks before
it dispatches fix(), so no prompt text can talk NEO past it."""
import re
import uuid
from pathlib import Path

from . import config, orchestrator, radar

SKILLS = Path(__file__).resolve().parent / "skills"
_SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_SKILL_CAP = 6000


class Session:
    """One chat session's live state: the run NEO is attacking and, once blue has
    run, the fix summary. Tools read and update it."""

    def __init__(self, *, repo: str | None = None, agent: str = "swarm", ask=None):
        self.repo = repo
        self.agent = agent          # "swarm" (real red models) or "mock" (offline)
        self.ask = ask              # chat_json-compatible callable for blue + reviewers
        self.ctx: dict | None = None
        self.findings: list | None = None
        self.summary: dict | None = None


def _swarm_models(n: int):
    fn = getattr(config, "swarm", None)
    if callable(fn):
        return fn(n)
    pool = list(config.RED_SWARM) + list(getattr(config, "RED_SWARM_EXTRA", []))
    return pool[: max(1, n)] if n else list(config.RED_SWARM)


def radar_scan(session: Session, limit: int = 5) -> dict:
    """Read-only: SBOM the target and rank the top KEV/CVE matches. No target contact."""
    scan = radar.scan()
    rows = scan.get("matches", [])[: max(1, limit)]
    keys = ("package", "version", "cve", "kev", "epss", "reachable")
    return {"kev_source": scan.get("kev_source"),
            "matches": [{k: m.get(k) for k in keys} for m in rows]}


def attack(session: Session, swarm: int = 3) -> dict:
    """Start a run and prove the exploits on disposable twins. Server-side flag
    checks decide, never a model. Sets the session's run and proven findings."""
    run_id = f"chat-{uuid.uuid4().hex[:8]}"
    # mock needs no real model ids; start() falls back to the reference chain
    models = None if session.agent == "mock" else _swarm_models(swarm)
    ctx = orchestrator.start(run_id, models=models, live=True,
                             agent=session.agent, ask=session.ask)
    findings = orchestrator.attack(ctx)
    session.ctx = ctx
    session.findings = findings
    keys = ("cls", "location", "confirmed_by", "found_by")
    return {"proven": len(findings),
            "findings": [{k: f.get(k) for k in keys} for f in findings]}


def fix(session: Session) -> dict:
    """Blue writes and verifies the patch on a fresh copy, two vendors review the
    diff, a fresh twin replays the exploit. Returns the PR, verdicts, retest and
    merge readiness. Needs a proven finding first."""
    if session.ctx is None or not session.findings:
        return {"error": "Nothing to fix yet. Run attack first and prove an exploit."}
    summary = orchestrator.remediate(session.ctx, repo=session.repo, screenshots=False)
    session.summary = summary
    return _fix_view(summary)


def status(session: Session) -> dict:
    """The current run's state: idle, exploit proven, or fixed and merge-ready."""
    if session.summary is not None:
        return _fix_view(session.summary)
    if session.ctx is not None:
        return {"run": session.ctx.get("id"),
                "proven": len(session.findings or []),
                "fixed": False}
    return {"state": "idle", "note": "No run yet. Say the word and I will attack the target."}


def read_skill(session: Session, name: str) -> dict:
    """Return one NEO methodology skill (neo/skills/<name>/SKILL.md), capped.
    Rejects anything that is not a bare skill directory name, so no path traversal."""
    if not _SKILL_NAME.match(name or ""):
        return {"error": f"no such skill: {name!r}"}
    path = SKILLS / name / "SKILL.md"
    try:
        resolved = path.resolve()
        resolved.relative_to(SKILLS.resolve())
    except (ValueError, OSError):
        return {"error": f"no such skill: {name!r}"}
    if not resolved.is_file():
        return {"error": f"no such skill: {name!r}"}
    return {"skill": name, "content": resolved.read_text()[:_SKILL_CAP]}


def _fix_view(summary: dict) -> dict:
    pr = summary.get("pr") or {}
    review = summary.get("review") or {}
    merge = summary.get("merge") or {}
    return {
        "pr": {k: pr.get(k) for k in ("url", "number", "mode")},
        "reviewers": [{"reviewer": v.get("reviewer"), "vendor": v.get("vendor"),
                       "verdict": v.get("verdict")} for v in review.get("verdicts", [])],
        "exploit_dead_on_patched_twin": (summary.get("retest") or {}).get("post_patch_green"),
        "tests": (summary.get("retest") or {}).get("tests"),
        "merge_ready": merge.get("ready"),
        "awaiting": merge.get("awaiting"),
    }


def _frontmatter(text: str) -> tuple[str, str]:
    """Pull `name` and `description` from a SKILL.md YAML front matter block."""
    if not text.startswith("---"):
        return "", ""
    block = text.split("---", 2)[1] if text.count("---") >= 2 else ""
    name = desc = ""
    for line in block.splitlines():
        if line.startswith("name:"):
            name = line.split(":", 1)[1].strip()
        elif line.startswith("description:"):
            desc = line.split(":", 1)[1].strip()
    return name, desc


def skill_index() -> dict:
    """name -> one-line, read from each skill's front matter at load time."""
    out = {}
    for skill_md in sorted(SKILLS.glob("*/SKILL.md")):
        name, desc = _frontmatter(skill_md.read_text())
        name = name or skill_md.parent.name
        first = re.split(r"(?<=[.])\s", desc.strip(), maxsplit=1)[0] if desc else ""
        out[name] = first
    return out


_FNS = {"radar_scan": radar_scan, "attack": attack, "fix": fix,
        "status": status, "read_skill": read_skill}

# OpenAI-compatible tool schemas passed to the chat model.
SCHEMAS = [
    {"type": "function", "function": {
        "name": "radar_scan",
        "description": "Scan the target's SBOM against KEV/CVE/EPSS/OSV and return the "
                       "top matches. Read-only, no contact with the target.",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "description": "max matches to return"}}}}},
    {"type": "function", "function": {
        "name": "attack",
        "description": "Prove what is exploitable: start a run and let the red swarm "
                       "attack disposable twins. A server-side flag check decides, never "
                       "a model's word. Returns each proven finding.",
        "parameters": {"type": "object", "properties": {
            "swarm": {"type": "integer",
                      "description": "how many open-weight red models to dispatch"}}}}},
    {"type": "function", "function": {
        "name": "fix",
        "description": "Write and verify the patch on a fresh copy, have two vendors review "
                       "the exact diff, and replay the exploit on a fresh twin (it must "
                       "fail). Only after a human approves. Returns the PR and merge "
                       "readiness.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "status",
        "description": "The current run's state: idle, exploit proven, or fixed.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "read_skill",
        "description": "Read one of NEO's methodology skills by name.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "the skill directory name"}},
            "required": ["name"]}}},
]


def call(session: Session, name: str, args: dict | None) -> dict:
    """Dispatch a tool by name. Returns a result dict; failures become `{error}`
    data for the model, never a raised exception."""
    fn = _FNS.get(name)
    if fn is None:
        return {"error": f"no such tool: {name!r}"}
    try:
        return fn(session, **(args or {}))
    except TypeError as e:
        return {"error": f"bad arguments for {name}: {e}"}
    except Exception as e:  # noqa: BLE001 - any tool failure is data for the model
        return {"error": f"{name} failed: {type(e).__name__}: {e}"}
