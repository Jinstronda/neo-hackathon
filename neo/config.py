"""NEO model map and gateway config. Everything comes from the env, and .env is
loaded here at import, so any entry point sees the same values.

The red swarm ids live only in the untracked .env (NEO_RED_SWARM), never in this
public file; UI and logs show them as model-1..model-n. Blue, reviewer and chat
ids were confirmed against the gateway's /v1/models on 2026-11-20 and can be
overridden from the env. Never hardcode a key or a gateway host here."""
import os

from . import env

env.load()


def _ids(name: str) -> list[str]:
    return [m.strip() for m in os.environ.get(name, "").split(",") if m.strip()]


GATEWAY_BASE = os.environ.get("NEO_GATEWAY_BASE") or "https://mcp.homodeus.co/llm/v1"
API_KEY_ENV = "HOMODEUS_API_KEY"

# The offensive side: open-weight models running on our own EU servers.
RED_SWARM = _ids("NEO_RED_SWARM")
# Extra engines for a wider swarm (up to five in total, per the design).
RED_SWARM_EXTRA = _ids("NEO_RED_SWARM_EXTRA")

# The blue side writes the fix.
BLUE_FIXER = os.environ.get("NEO_BLUE_FIXER") or "openai/gpt-5.3-codex"

# Two-vendor review of the exact diff. Each reviewer re-runs its claim before posting.
REVIEWER_SECURITY = os.environ.get("NEO_REVIEWER_SECURITY") or "openai/gpt-6.2-sol"
REVIEWER_CORRECTNESS = os.environ.get("NEO_REVIEWER_CORRECTNESS") or "claude-sonnet-5-5"

# The terminal agent and the loop narration.
CHAT_MODEL = os.environ.get("NEO_CHAT_MODEL") or "gpt-6-luna"

# Where the fix PR opens; `neo run --local` and `neo watch --local` skip GitHub.
GITHUB_REPO = os.environ.get("NEO_REPO") or "Jinstronda/neo-hackathon"

PROJECT_HEADER = "neo-hackathon"

SWARM_UNSET = ("NEO_RED_SWARM is empty. Set it in .env to a comma-separated list of "
               "red model ids (see .env.example).")


def swarm(n: int | None = None) -> list[str]:
    """The first n red models, primary swarm first, then the extras. None means the
    whole primary swarm. Raises with one clear message when NEO_RED_SWARM is unset."""
    if not RED_SWARM:
        raise RuntimeError(SWARM_UNSET)
    return (RED_SWARM + RED_SWARM_EXTRA)[:n] if n else list(RED_SWARM)
