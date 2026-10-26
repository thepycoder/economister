"""Anthropic Messages API wrappers for curator and correspondent stages."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import anthropic

from belgium.config import (
    AGENT_MAX_OUTPUT_TOKENS,
    ANTHROPIC_API_KEY,
    BELGIUM_EFFORT,
    BELGIUM_MODEL,
    BELGIUM_WRITER_MODEL,
    MAX_PAUSE_CONTINUATIONS,
    WRITER_MAX_WEB_SEARCHES,
)

# Classifier refusals are retried server-side on Anthropic's recommended model.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# List prices in USD per million tokens: (input, output, cache write, cache read).
# Fallback models are listed so a rescued call is still priced.
MODEL_PRICES_PER_MTOK = {
    "claude-opus-5-5": (4.00, 20.00, 5.00, 0.20),
    "claude-opus-5": (5.00, 25.00, 6.25, 0.50),
    "claude-opus-4-8": (5.00, 25.00, 6.25, 0.50),
}
WEB_SEARCH_USD = 0.01  # $10 per 1,000 searches


class AgentError(RuntimeError):
    """Raised when an Anthropic model call fails."""


PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def load_prompt(name: str, **replacements: Any) -> str:
    """Load a prompt markdown file and substitute ``{{KEY}}`` placeholders."""
    path = PROMPTS_DIR / name
    text = path.read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


def extract_json_object(text: str) -> Dict[str, Any]:
    """Parse a JSON object from model output, tolerating markdown fences."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start:end + 1]
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AgentError(f"Model did not return valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AgentError("Model JSON root must be an object")
    return data


def _require_api_key(api_key: Optional[str] = None) -> str:
    key = (api_key if api_key is not None else ANTHROPIC_API_KEY).strip()
    if not key:
        raise AgentError(
            "ANTHROPIC_API_KEY is not set. Add it to .env or the environment."
        )
    return key


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _maybe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def effective_cost_usd(usage: Dict[str, Any]) -> Optional[float]:
    """Stage cost in USD: the recorded effective cost, else the raw cost.

    Runs from the OpenRouter era stored a BYOK-adjusted ``effective_cost_usd``;
    reading it first keeps their roll-ups unchanged.
    """
    for key in ("effective_cost_usd", "cost_usd"):
        value = _maybe_float(usage.get(key))
        if value is not None:
            return value
    return None


def estimate_cost_usd(model: Optional[str], usage: Any) -> Optional[float]:
    """Price one response's usage at list rates; ``None`` for unpriced models."""
    prices = MODEL_PRICES_PER_MTOK.get(model or "")
    if prices is None:
        return None
    input_price, output_price, write_price, read_price = prices
    token_cost = (
        (_field(usage, "input_tokens") or 0) * input_price
        + (_field(usage, "output_tokens") or 0) * output_price
        + (_field(usage, "cache_creation_input_tokens") or 0) * write_price
        + (_field(usage, "cache_read_input_tokens") or 0) * read_price
    ) / 1_000_000
    searches = _field(_field(usage, "server_tool_use"), "web_search_requests") or 0
    return token_cost + searches * WEB_SEARCH_USD


def usage_from_responses(responses: List[Any]) -> Dict[str, Any]:
    """Sum usage across one call's responses (paused turns resume in new ones)."""
    last = responses[-1]
    tokens_prompt = 0
    tokens_completion = 0
    searches = 0
    cost: Optional[float] = 0.0
    for response in responses:
        usage = response.usage
        tokens_prompt += (
            (_field(usage, "input_tokens") or 0)
            + (_field(usage, "cache_creation_input_tokens") or 0)
            + (_field(usage, "cache_read_input_tokens") or 0)
        )
        tokens_completion += _field(usage, "output_tokens") or 0
        searches += (
            _field(_field(usage, "server_tool_use"), "web_search_requests") or 0
        )
        part = estimate_cost_usd(response.model, usage)
        cost = None if cost is None or part is None else cost + part
    return {
        "generation_id": last.id,
        "model": last.model,
        "provider": "anthropic",
        "cost_usd": cost,
        "effective_cost_usd": cost,
        "tokens_prompt": tokens_prompt,
        "tokens_completion": tokens_completion,
        "web_search_requests": searches,
    }


def _call_model_text(
    *,
    model: str,
    prompt: str,
    tools: Optional[List[Dict[str, Any]]] = None,
    api_key: Optional[str] = None,
    effort: Optional[str] = None,
    max_output_tokens: Optional[int] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Run one model call to completion and return (text, usage_meta)."""
    client = anthropic.Anthropic(api_key=_require_api_key(api_key), max_retries=4)
    max_tokens = max_output_tokens or AGENT_MAX_OUTPUT_TOKENS
    request: Dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "output_config": {"effort": effort or BELGIUM_EFFORT},
        "betas": [FALLBACK_BETA],
        "fallbacks": "default",
    }
    if tools:
        request["tools"] = tools

    messages: List[Dict[str, Any]] = [{"role": "user", "content": prompt}]
    responses: List[Any] = []
    for _ in range(MAX_PAUSE_CONTINUATIONS + 1):
        # Stream so long research turns are not cut off by HTTP timeouts.
        with client.beta.messages.stream(messages=messages, **request) as stream:
            response = stream.get_final_message()
        responses.append(response)
        if response.stop_reason != "pause_turn":
            break
        # The server resumes its web-search loop from the trailing tool use.
        messages.append({"role": "assistant", "content": response.content})

    usage = usage_from_responses(responses)
    stop_reason = response.stop_reason
    if stop_reason == "refusal":
        category = _field(response.stop_details, "category")
        raise AgentError(f"{response.model} declined the request ({category})")
    if stop_reason == "pause_turn":
        raise AgentError(
            f"Web search still running after {MAX_PAUSE_CONTINUATIONS} continuations"
        )
    if stop_reason == "max_tokens":
        raise AgentError(f"Response hit max_tokens ({max_tokens}) before finishing")

    text = "".join(block.text for block in response.content if block.type == "text")
    if not text.strip():
        raise AgentError("Anthropic returned an empty response")
    return text, usage


def run_curator(
    *,
    source_index_json: str,
    max_topics: int = 5,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    article_excerpts: Optional[str] = None,
    excluded_topics: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Ask the curator model for a shortlist JSON object.

    Returns ``(parsed_json, usage_meta)``.
    """
    excluded = (excluded_topics or "").strip() or "_None yet — this is a fresh run._"
    prompt = load_prompt(
        "curator.md",
        MAX_TOPICS=max_topics,
        EXCLUDED_TOPICS=excluded,
    )
    prompt += "\n\n## Source index\n\n```json\n"
    prompt += source_index_json
    prompt += "\n```\n"
    if article_excerpts:
        prompt += "\n## Article excerpts\n\n"
        prompt += article_excerpts
        prompt += "\n"

    text, usage = _call_model_text(
        model=model or BELGIUM_MODEL,
        prompt=prompt,
        api_key=api_key,
    )
    return extract_json_object(text), usage


def run_writer(
    *,
    shortlist_json: str,
    source_pack: str,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    enable_web_search: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Ask the correspondent model to research and write articles.

    Returns ``(parsed_json, usage_meta)``. The JSON may be a single article
    object or ``{"articles": [...]}``.
    """
    prompt = load_prompt("writer.md")
    prompt += "\n\n## Shortlist\n\n```json\n"
    prompt += shortlist_json
    prompt += "\n```\n\n## VRT source pack\n\n"
    prompt += source_pack
    prompt += "\n"

    tools = None
    if enable_web_search:
        tools = [{
            "type": "web_search_20260209",
            "name": "web_search",
            "max_uses": WRITER_MAX_WEB_SEARCHES,
            "user_location": {
                "type": "approximate",
                "country": "BE",
                "timezone": "Europe/Brussels",
            },
        }]

    text, usage = _call_model_text(
        model=model or BELGIUM_WRITER_MODEL,
        prompt=prompt,
        tools=tools,
        api_key=api_key,
    )
    return extract_json_object(text), usage


def normalize_writer_payload(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Accept either ``{articles: [...]}`` or a single article object."""
    if "articles" in data and isinstance(data["articles"], list):
        return [item for item in data["articles"] if isinstance(item, dict)]
    if "title" in data and "paragraphs" in data:
        return [data]
    raise AgentError(
        "Writer JSON must be an article object or {\"articles\": [...]}"
    )


def unpack_agent_result(
    result: Tuple[Any, ...],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Normalize agent return values from ``(data, usage)`` or legacy ``(data, id)``."""
    if not isinstance(result, tuple) or len(result) < 2:
        raise AgentError("Agent call must return (data, usage_meta)")
    data = result[0]
    meta = result[1]
    if isinstance(meta, dict):
        return data, meta
    if meta is None or isinstance(meta, str):
        return data, {"generation_id": meta}
    raise AgentError("Unexpected agent usage metadata type")
