"""Configuration for the Belgium news pipeline."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
BELGIUM_MODEL = os.getenv("BELGIUM_MODEL", "").strip() or "claude-opus-5-5"
BELGIUM_WRITER_MODEL = os.getenv(
    "BELGIUM_WRITER_MODEL",
    "",
).strip() or BELGIUM_MODEL
# Opus 5.5 defaults to "medium"; curating and writing the briefing want more.
BELGIUM_EFFORT = os.getenv("BELGIUM_EFFORT", "").strip() or "high"

BELGIUM_RUNS_DIR = PROJECT_ROOT / "belgium_runs"

# Agent call caps
WRITER_MAX_WEB_SEARCHES = 8
# The server pauses long web-search loops (stop_reason "pause_turn").
MAX_PAUSE_CONTINUATIONS = 3
# Thinking tokens count against this budget; keep headroom for the article.
AGENT_MAX_OUTPUT_TOKENS = 64_000

# VRT ingest defaults
DEFAULT_LOOKBACK_DAYS = 7
DEFAULT_MAX_TOPICS = 5
PREFERRED_CATEGORIES = (
    "binnenland",
    "analyse",
    "milieu-en-klimaat",
    "technologie-en-wetenschap",
    "buitenland",
)
SKIP_CATEGORIES = frozenset({"sport", "royalty"})
