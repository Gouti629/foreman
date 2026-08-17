import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")
DB_PATH = os.environ.get("FOREMAN_DB_PATH", "foreman.db")

# Severity -> numeric weight, used by the deterministic synthesis scorer.
# Kept in one place so routing thresholds and synthesis thresholds agree.
SEVERITY_WEIGHT = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

# A specialist verdict counts as a "hard fail" for routing purposes when its
# worst finding is at least this severe and the specialist is at least this
# confident in it. Hard fails from coverage or consistency short-circuit the
# pricing check (see app/agents/orchestrator.py).
HARD_FAIL_SEVERITY = "critical"
HARD_FAIL_MIN_CONFIDENCE = 0.7
