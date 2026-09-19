"""OpenRouter Agent SDK wrappers for curator and correspondent stages."""

from __future__ import annotations

import asyncio
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from belgium.config import (
    AGENT_MAX_OUTPUT_TOKENS,
    CURATOR_MAX_COST_USD,
    CURATOR_MAX_STEPS,
    OPENROUTER_API_KEY,
    OPENROUTER_BELGIUM_MODEL,
    OPENROUTER_BELGIUM_REASONING_EFFORT,
    OPENROUTER_BELGIUM_WRITER_MODEL,
    WRITER_MAX_COST_USD,
    WRITER_MAX_STEPS,
)

GENERATION_API = "https://openrouter.ai/api/v1/generation"


class AgentError(RuntimeError):
    """Raised when an OpenRouter agent call fails."""


def _ensure_openrouter_compat() -> None:
    """Shim missing symbols so openrouter-agent-sdk 0.8 can import.

    openrouter 1.2.x removed ``OutputImage`` which the agent package still
    imports. Alias it to ``InputImage`` before loading ``openrouter_agent``.
    """
    import openrouter.components as components

    if not hasattr(components, "OutputImage"):
        from openrouter.components import InputImage

        components.OutputImage = InputImage


def _import_agent():
    """Import openrouter_agent after applying the compatibility shim."""
    _ensure_openrouter_compat()
    from openrouter_agent import (  # noqa: WPS433
        OpenRouter,
        call_model,
        max_cost,
        server_tool,
        step_count_is,
    )

    return OpenRouter, call_model, max_cost, server_tool, step_count_is


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
    key = (api_key if api_key is not None else OPENROUTER_API_KEY).strip()
    if not key:
        raise AgentError(
            "OPENROUTER_API_KEY is not set. Add it to .env or the environment."
        )
    return key


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def effective_cost_usd(usage: Dict[str, Any]) -> Optional[float]:
    """Prefer billed OpenRouter cost; fall back to BYOK upstream estimate.

    With Bring-Your-Own-Key, OpenRouter often reports ``total_cost``/``usage``
    as ``0`` while still populating ``upstream_inference_cost``.
    """
    billed = _maybe_float(usage.get("cost_usd"))
    upstream = _maybe_float(usage.get("upstream_inference_cost_usd"))
    is_byok = bool(usage.get("is_byok"))

    if is_byok or (billed == 0.0 and upstream is not None):
        return upstream if upstream is not None else billed
    if billed is not None:
        return billed
    return upstream


def fetch_generation_usage(
    generation_id: str,
    *,
    api_key: Optional[str] = None,
    retries: int = 4,
    delay_seconds: float = 1.5,
) -> Dict[str, Any]:
    """Look up cost/token stats for a finished OpenRouter generation."""
    key = _require_api_key(api_key)
    url = f"{GENERATION_API}?id={urllib.parse.quote(generation_id)}"
    last_error: Optional[Exception] = None

    for attempt in range(retries):
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {key}",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, dict):
                data = payload if isinstance(payload, dict) else {}
            return normalize_generation_usage(data, generation_id=generation_id)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(delay_seconds * (attempt + 1))
    raise AgentError(
        f"Failed to fetch generation stats for {generation_id}: {last_error}"
    )


def normalize_generation_usage(
    data: Dict[str, Any],
    *,
    generation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Normalize OpenRouter generation metadata into a stable usage dict."""
    total_cost = data.get("total_cost")
    if total_cost is None:
        total_cost = data.get("usage")
    upstream = data.get("upstream_inference_cost")
    usage = {
        "generation_id": data.get("id") or generation_id,
        "model": data.get("model"),
        "provider": data.get("provider_name"),
        "is_byok": bool(data.get("is_byok")),
        "cost_usd": _maybe_float(total_cost),
        "upstream_inference_cost_usd": _maybe_float(upstream),
        "tokens_prompt": data.get("native_tokens_prompt") or data.get("tokens_prompt"),
        "tokens_completion": (
            data.get("native_tokens_completion") or data.get("tokens_completion")
        ),
        "web_search_engine": data.get("web_search_engine"),
        "latency_ms": data.get("latency"),
        "generation_time_ms": data.get("generation_time"),
    }
    usage["effective_cost_usd"] = effective_cost_usd(usage)
    return usage


def _maybe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _usage_from_response(response: Any) -> Dict[str, Any]:
    """Best-effort usage extraction from the live Responses payload."""
    usage_block = _field(response, "usage") or {}
    generation_id = _field(response, "id") or _field(_field(response, "meta"), "id")
    cost = _field(usage_block, "cost")
    return {
        "generation_id": generation_id,
        "model": _field(response, "model"),
        "cost_usd": _maybe_float(cost),
        "tokens_prompt": _field(usage_block, "input_tokens") or _field(usage_block, "prompt_tokens"),
        "tokens_completion": (
            _field(usage_block, "output_tokens") or _field(usage_block, "completion_tokens")
        ),
        "effective_cost_usd": _maybe_float(cost),
    }


async def _call_model_text(
    *,
    model: str,
    prompt: str,
    tools: Optional[List[Any]] = None,
    max_steps: int = 8,
    max_cost_usd: float = 1.0,
    api_key: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
    max_output_tokens: Optional[int] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Run one ``call_model`` loop and return (text, usage_meta)."""
    OpenRouter, call_model, max_cost, _server_tool, step_count_is = _import_agent()
    key = _require_api_key(api_key)
    client = OpenRouter(api_key=key)

    effort = (reasoning_effort or OPENROUTER_BELGIUM_REASONING_EFFORT).strip()
    request: Dict[str, Any] = {
        "model": model,
        "input": prompt,
        "stop_when": [step_count_is(max_steps), max_cost(max_cost_usd)],
        "max_output_tokens": max_output_tokens or AGENT_MAX_OUTPUT_TOKENS,
    }
    if effort and effort.lower() not in {"none", "off", "disabled"}:
        # Gemini 3: OpenRouter maps effort → Google thinkingLevel (max is "high").
        request["reasoning"] = {"effort": effort}
    if tools:
        request["tools"] = tools

    result = call_model(client, request)
    text = await result.get_text()
    usage: Dict[str, Any] = {}
    try:
        response = await result.get_response()
        usage = _usage_from_response(response)
    except Exception:
        usage = {}

    generation_id = usage.get("generation_id")
    if generation_id:
        try:
            # Generation stats (esp. BYOK upstream cost) often lag the stream.
            await asyncio.sleep(1.0)
            fetched = await asyncio.to_thread(
                fetch_generation_usage,
                str(generation_id),
                api_key=key,
            )
            usage = {**usage, **{k: v for k, v in fetched.items() if v is not None}}
            usage["effective_cost_usd"] = effective_cost_usd(usage)
        except AgentError:
            pass

    if not text or not str(text).strip():
        raise AgentError("OpenRouter returned an empty response")
    return str(text), usage


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

    text, usage = asyncio.run(
        _call_model_text(
            model=model or OPENROUTER_BELGIUM_MODEL,
            prompt=prompt,
            tools=None,
            max_steps=CURATOR_MAX_STEPS,
            max_cost_usd=CURATOR_MAX_COST_USD,
            api_key=api_key,
        )
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
    _OpenRouter, _call_model, _max_cost, server_tool, _step_count_is = _import_agent()

    prompt = load_prompt("writer.md")
    prompt += "\n\n## Shortlist\n\n```json\n"
    prompt += shortlist_json
    prompt += "\n```\n\n## VRT source pack\n\n"
    prompt += source_pack
    prompt += "\n"

    tools = None
    if enable_web_search:
        tools = [
            server_tool({
                "type": "openrouter:web_search",
                "parameters": {
                    "engine": "auto",
                    "max_results": 5,
                    "max_uses": 8,
                    "user_location": {
                        "type": "approximate",
                        "country": "BE",
                        "timezone": "Europe/Brussels",
                    },
                },
            })
        ]

    text, usage = asyncio.run(
        _call_model_text(
            model=model or OPENROUTER_BELGIUM_WRITER_MODEL,
            prompt=prompt,
            tools=tools,
            max_steps=WRITER_MAX_STEPS,
            max_cost_usd=WRITER_MAX_COST_USD,
            api_key=api_key,
        )
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
