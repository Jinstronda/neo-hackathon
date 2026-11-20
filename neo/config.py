"""NEO model map and gateway config. Ids confirmed against the HomoDeus LLM
gateway /v1/models on 2026-11-20. Never hardcode a key here; read the env."""
import os

GATEWAY_BASE = os.environ.get("NEO_GATEWAY_BASE", "https://mcp.homodeus.co/llm/v1")
API_KEY_ENV = "HOMODEUS_API_KEY"

# The offensive side. Open-weight models that run on our own EU servers.
# In public UI/README these are described, never named individually.
RED_SWARM = [
    "refuseless/glm-5.3-abliterated",
    "refuseless/deepseek-v4.1-flash-abliterated",
    "refuseless/minimax-m3.1-flash",
]
# Extra engines if more breadth is wanted (up to five, per the design).
RED_SWARM_EXTRA = [
    "refuseless/kimi-k3.1-pro-abliterated",
    "refuseless/glm-5.3-flash-abliterated",
]

# The blue side writes the fix.
BLUE_FIXER = "openai/gpt-5.3-codex"

# Two-vendor PR review. Each reviewer re-runs its claim before posting.
REVIEWER_SECURITY = "openai/gpt-6.2-sol"      # OpenAI
REVIEWER_CORRECTNESS = "claude-sonnet-5-5"    # Anthropic (SOTA; sonnet 5.5 per João 2026-11-20)

# The agentic chat / orchestrator narration (frontier, cheap).
CHAT_MODEL = "gpt-6-luna"

PROJECT_HEADER = "neo-hackathon"
