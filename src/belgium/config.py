"""Configuration for the Belgium news pipeline."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_BELGIUM_MODEL = os.getenv(
    "OPENROUTER_BELGIUM_MODEL",
    "openai/gpt-5.6-sol",
).strip()
OPENROUTER_BELGIUM_WRITER_MODEL = os.getenv(
    "OPENROUTER_BELGIUM_WRITER_MODEL",
    "",
).strip() or OPENROUTER_BELGIUM_MODEL
# Gemini 3 maps effort → thinkingLevel; "high" is the ceiling (xhigh → high).
OPENROUTER_BELGIUM_REASONING_EFFORT = os.getenv(
    "OPENROUTER_BELGIUM_REASONING_EFFORT",
    "high",
).strip() or "high"

BELGIUM_RUNS_DIR = PROJECT_ROOT / "belgium_runs"

# Agent loop caps
CURATOR_MAX_STEPS = 4
WRITER_MAX_STEPS = 12
CURATOR_MAX_COST_USD = 0.50
WRITER_MAX_COST_USD = 8.00
# Reasoning tokens count against this budget; keep headroom for the article.
AGENT_MAX_OUTPUT_TOKENS = 16_000

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
