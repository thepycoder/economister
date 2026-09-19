"""Belgium pipeline stage machine: ingest → curate → write."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from belgium import agents as agent_api
from belgium.config import (
    BELGIUM_RUNS_DIR,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MAX_TOPICS,
    OPENROUTER_BELGIUM_MODEL,
)
from belgium.models import (
    BelgiumArticle,
    RunState,
    Shortlist,
    SourceIndex,
    utc_now_iso,
    validate_article,
    validate_shortlist,
)
from belgium.vrt_client import VrtClient, collect_week, write_source_pack

STAGES = ("ingest", "curate", "write")
SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"


class PipelineError(RuntimeError):
    """Raised when a pipeline stage fails."""


def new_run_dir(base: Optional[Path] = None, date_stamp: Optional[str] = None) -> Path:
    """Create a fresh run directory under ``belgium_runs/``."""
    root = base or BELGIUM_RUNS_DIR
    root.mkdir(parents=True, exist_ok=True)
    stamp = date_stamp or utc_now_iso()[:10]
    path = root / stamp
    if path.exists():
        # Avoid clobbering an existing run; append a counter.
        n = 2
        while (root / f"{stamp}-{n}").exists():
            n += 1
        path = root / f"{stamp}-{n}"
    path.mkdir(parents=True, exist_ok=False)
    _seed_run_dir(path)
    return path


def _seed_run_dir(run_dir: Path) -> None:
    """Copy schemas into the run folder for human inspection."""
    dest = run_dir / "schemas"
    dest.mkdir(parents=True, exist_ok=True)
    for schema in SCHEMAS_DIR.glob("*.json"):
        shutil.copy2(schema, dest / schema.name)


def _run_state_path(run_dir: Path) -> Path:
    return run_dir / "run.json"


def load_or_create_state(run_dir: Path, model: str) -> RunState:
    """Load ``run.json`` or create a new one."""
    path = _run_state_path(run_dir)
    if path.exists():
        return RunState.load(path)
    state = RunState(
        run_dir=str(run_dir),
        created_at=utc_now_iso(),
        model=model,
        stages={},
    )
    state.save(path)
    return state


def mark_stage(
    state: RunState,
    stage: str,
    *,
    status: str,
    generation_id: Optional[str] = None,
    detail: Optional[str] = None,
    usage: Optional[Dict[str, Any]] = None,
) -> None:
    """Update and persist stage status."""
    entry: Dict[str, Any] = {
        "status": status,
        "updated_at": utc_now_iso(),
    }
    if generation_id:
        entry["generation_id"] = generation_id
    if detail:
        entry["detail"] = detail
    if usage:
        entry["usage"] = usage
    state.stages[stage] = entry
    _refresh_run_cost(state)
    state.save(Path(state.run_dir) / "run.json")


def _refresh_run_cost(state: RunState) -> None:
    """Roll up per-stage usage into ``state.cost``."""
    stages_cost: Dict[str, Any] = {}
    total = 0.0
    has_any = False
    byok = False
    for name, entry in state.stages.items():
        usage = entry.get("usage") if isinstance(entry, dict) else None
        if not isinstance(usage, dict):
            continue
        amount = agent_api.effective_cost_usd(usage)
        stage_info = {
            "generation_id": usage.get("generation_id") or entry.get("generation_id"),
            "cost_usd": usage.get("cost_usd"),
            "upstream_inference_cost_usd": usage.get("upstream_inference_cost_usd"),
            "effective_cost_usd": amount,
            "tokens_prompt": usage.get("tokens_prompt"),
            "tokens_completion": usage.get("tokens_completion"),
            "is_byok": usage.get("is_byok"),
            "web_search_engine": usage.get("web_search_engine"),
        }
        stages_cost[name] = stage_info
        if usage.get("is_byok"):
            byok = True
        if amount is not None:
            total += amount
            has_any = True
    state.cost = {
        "currency": "USD",
        "total_usd": round(total, 6) if has_any else None,
        "is_byok": byok,
        "note": (
            "BYOK: OpenRouter billed $0; total_usd uses upstream_inference_cost"
            if byok
            else None
        ),
        "stages": stages_cost,
    }


def stage_ingest(
    run_dir: Path,
    *,
    days: int = DEFAULT_LOOKBACK_DAYS,
    client: Optional[VrtClient] = None,
    fetch_bodies: bool = True,
    model: Optional[str] = None,
) -> SourceIndex:
    """Fetch VRT sources into ``run_dir/sources/``."""
    state = load_or_create_state(run_dir, model or OPENROUTER_BELGIUM_MODEL)
    mark_stage(state, "ingest", status="running")
    try:
        index = collect_week(days=days, client=client, fetch_bodies=fetch_bodies)
        write_source_pack(index, run_dir)
        mark_stage(
            state,
            "ingest",
            status="ok",
            detail=f"{len(index.articles)} articles",
        )
        return index
    except Exception as exc:
        mark_stage(state, "ingest", status="error", detail=str(exc))
        raise


def _index_for_prompt(index: SourceIndex) -> str:
    """Compact JSON for the curator (omit long bodies)."""
    compact = {
        "fetched_at": index.fetched_at,
        "days": index.days,
        "articles": [
            {
                "title": a.title,
                "url": a.url,
                "published": a.published,
                "category": a.category,
                "summary": a.summary,
            }
            for a in index.articles
        ],
    }
    return json.dumps(compact, indent=2, ensure_ascii=False)


def _excerpts_for_prompt(index: SourceIndex, limit: int = 40, max_chars: int = 1200) -> str:
    """Short body excerpts so the curator can cluster better."""
    parts: List[str] = []
    for article in index.articles[:limit]:
        body = (article.body or article.summary or "").strip()
        if not body:
            continue
        if len(body) > max_chars:
            body = body[:max_chars].rstrip() + "…"
        parts.append(f"### {article.title}\nURL: {article.url}\n\n{body}\n")
    return "\n".join(parts)


def load_existing_articles(run_dir: Path) -> List[BelgiumArticle]:
    """Load articles already written into this run directory."""
    articles_dir = run_dir / "articles"
    if not articles_dir.exists():
        return []
    articles: List[BelgiumArticle] = []
    for path in sorted(articles_dir.glob("*.json")):
        try:
            articles.append(BelgiumArticle.load(path))
        except (OSError, json.JSONDecodeError, TypeError, ValueError, KeyError):
            continue
    return articles


def existing_slugs(run_dir: Path) -> set[str]:
    """Slugs that already have an article JSON in this run."""
    return {a.slug for a in load_existing_articles(run_dir) if a.slug}


def format_excluded_topics(articles: List[BelgiumArticle]) -> str:
    """Human/model-readable list of topics already covered in this run."""
    if not articles:
        return "_None yet — this is a fresh run._"
    lines: List[str] = []
    for article in articles:
        lines.append(f"- `{article.slug}`: {article.title}")
        if article.topic_rationale:
            lines.append(f"  Rationale: {article.topic_rationale}")
        urls = [s.url for s in article.sources if s.url][:5]
        if urls:
            lines.append("  Sources: " + "; ".join(urls))
    return "\n".join(lines)


def filter_duplicate_topics(
    shortlist: Shortlist,
    *,
    excluded_slugs: set[str],
    excluded_source_urls: Optional[set[str]] = None,
) -> Shortlist:
    """Drop topics that collide with already-written articles.

    A topic is treated as a duplicate when its slug matches an existing article
    or when a majority of its VRT source URLs already appear in a prior piece.
    """
    excluded_urls = {u.rstrip("/") for u in (excluded_source_urls or set())}
    kept = []
    for topic in shortlist.topics:
        if topic.slug in excluded_slugs:
            continue
        topic_urls = {u.rstrip("/") for u in topic.source_urls if u}
        if topic_urls and excluded_urls:
            overlap = topic_urls & excluded_urls
            if len(overlap) >= max(1, (len(topic_urls) + 1) // 2):
                continue
        kept.append(topic)
    return Shortlist(topics=kept, notes=shortlist.notes)


def stage_curate(
    run_dir: Path,
    *,
    max_topics: int = DEFAULT_MAX_TOPICS,
    model: Optional[str] = None,
    curator_fn=None,
) -> Shortlist:
    """Run the curator agent and write ``shortlist.json``."""
    index_path = run_dir / "sources" / "index.json"
    if not index_path.exists():
        raise PipelineError(f"Missing {index_path}; run ingest first")

    index = SourceIndex.load(index_path)
    existing = load_existing_articles(run_dir)
    excluded = existing_slugs(run_dir)
    excluded_urls = {
        s.url.rstrip("/")
        for article in existing
        for s in article.sources
        if s.url
    }
    state = load_or_create_state(run_dir, model or OPENROUTER_BELGIUM_MODEL)
    mark_stage(state, "curate", status="running")

    call = curator_fn or agent_api.run_curator
    try:
        data, usage = agent_api.unpack_agent_result(call(
            source_index_json=_index_for_prompt(index),
            max_topics=max_topics,
            model=model,
            article_excerpts=_excerpts_for_prompt(index),
            excluded_topics=format_excluded_topics(existing),
        ))
        generation_id = usage.get("generation_id")
        errors = validate_shortlist(data, max_topics=max_topics)
        if errors:
            # One retry with validation feedback.
            retry_prompt_extra = (
                "Your previous JSON failed validation:\n- "
                + "\n- ".join(errors)
                + "\n\nReturn corrected JSON only."
            )
            data, usage = agent_api.unpack_agent_result(call(
                source_index_json=_index_for_prompt(index),
                max_topics=max_topics,
                model=model,
                article_excerpts=(
                    _excerpts_for_prompt(index) + "\n\n" + retry_prompt_extra
                ),
                excluded_topics=format_excluded_topics(existing),
            ))
            generation_id = usage.get("generation_id")
            errors = validate_shortlist(data, max_topics=max_topics)
            if errors:
                raise PipelineError("Curator validation failed: " + "; ".join(errors))

        shortlist = Shortlist.from_dict(data)
        shortlist.topics = shortlist.topics[:max_topics]
        shortlist = filter_duplicate_topics(
            shortlist,
            excluded_slugs=excluded,
            excluded_source_urls=excluded_urls,
        )
        if not shortlist.topics:
            raise PipelineError(
                "Curator returned only topics that duplicate existing articles; "
                "try again or widen the source window"
            )
        shortlist.save(run_dir / "shortlist.json")
        mark_stage(
            state,
            "curate",
            status="ok",
            generation_id=generation_id,
            detail=f"{len(shortlist.topics)} topics",
            usage=usage,
        )
        return shortlist
    except Exception as exc:
        mark_stage(state, "curate", status="error", detail=str(exc))
        raise


def _source_pack_for_topics(run_dir: Path, shortlist: Shortlist) -> str:
    """Build a markdown pack of VRT bodies relevant to the shortlist."""
    index = SourceIndex.load(run_dir / "sources" / "index.json")
    wanted = {u.rstrip("/") for topic in shortlist.topics for u in topic.source_urls}
    by_url = {a.url.rstrip("/"): a for a in index.articles}

    selected = [by_url[u] for u in wanted if u in by_url]
    if not selected:
        # Prefer not to dump the whole week into a single-topic write call.
        selected = list(index.articles[:8])

    parts: List[str] = []
    for article in selected:
        parts.append(f"## {article.title}")
        parts.append(f"URL: {article.url}")
        if article.published:
            parts.append(f"Published: {article.published}")
        if article.category:
            parts.append(f"Category: {article.category}")
        parts.append("")
        parts.append(article.body or article.summary or "_(no body)_")
        parts.append("")
    return "\n".join(parts)


def _merge_usage(parts: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Sum per-article writer usage into one stage-level usage dict."""
    if not parts:
        return {}
    if len(parts) == 1:
        return dict(parts[0])

    merged: Dict[str, Any] = {
        "generation_id": parts[0].get("generation_id"),
        "model": parts[0].get("model"),
        "provider": parts[0].get("provider"),
        "is_byok": any(bool(p.get("is_byok")) for p in parts),
        "articles": parts,
    }
    for key in (
        "cost_usd",
        "upstream_inference_cost_usd",
        "effective_cost_usd",
        "tokens_prompt",
        "tokens_completion",
    ):
        total = 0.0
        saw = False
        for part in parts:
            value = part.get(key)
            if value is None:
                continue
            try:
                total += float(value)
                saw = True
            except (TypeError, ValueError):
                continue
        if saw:
            merged[key] = total if key.endswith("_usd") else int(total)
    if "effective_cost_usd" not in merged:
        merged["effective_cost_usd"] = agent_api.effective_cost_usd(merged)
    return merged


def _write_one_topic(
    *,
    run_dir: Path,
    topic_shortlist: Shortlist,
    model: Optional[str],
    writer_fn,
) -> Tuple[BelgiumArticle, Dict[str, Any]]:
    """Research+write a single topic in an isolated model call."""
    topic = topic_shortlist.topics[0]
    shortlist_json = json.dumps(topic_shortlist.to_dict(), indent=2, ensure_ascii=False)
    source_pack = _source_pack_for_topics(run_dir, topic_shortlist)

    data, usage = agent_api.unpack_agent_result(writer_fn(
        shortlist_json=shortlist_json,
        source_pack=source_pack,
        model=model,
    ))
    raw_articles = agent_api.normalize_writer_payload(data)
    errors = _validate_writer_articles(raw_articles, expected_slug=topic.slug)

    if errors:
        retry_note = (
            "Validation failed:\n- "
            + "\n- ".join(errors)
            + "\n\nReturn a corrected JSON object with an articles array "
            "containing exactly one article for this topic."
        )
        data, usage = agent_api.unpack_agent_result(writer_fn(
            shortlist_json=shortlist_json,
            source_pack=source_pack + "\n\n" + retry_note,
            model=model,
        ))
        raw_articles = agent_api.normalize_writer_payload(data)
        errors = _validate_writer_articles(raw_articles, expected_slug=topic.slug)
        if errors:
            raise PipelineError(
                f"Writer validation failed for {topic.slug}: " + " | ".join(errors)
            )

    article = BelgiumArticle.from_dict(raw_articles[0])
    per_article_usage = dict(usage)
    per_article_usage["slug"] = article.slug
    return article, per_article_usage


def _validate_writer_articles(
    raw_articles: List[Dict[str, Any]],
    *,
    expected_slug: str,
) -> List[str]:
    """Validate a single-topic writer payload."""
    errors: List[str] = []
    if len(raw_articles) != 1:
        errors.append(
            f"expected exactly 1 article, got {len(raw_articles)}"
        )
        return errors
    item = raw_articles[0]
    errs = validate_article(item)
    if errs:
        errors.extend(errs)
    slug = item.get("slug")
    if slug and slug != expected_slug:
        errors.append(f"slug {slug!r} does not match topic {expected_slug!r}")
    return errors


def stage_write(
    run_dir: Path,
    *,
    model: Optional[str] = None,
    writer_fn=None,
) -> List[BelgiumArticle]:
    """Write each shortlist topic via its own isolated research+write call."""
    shortlist_path = run_dir / "shortlist.json"
    if not shortlist_path.exists():
        raise PipelineError(f"Missing {shortlist_path}; run curate first")

    shortlist = Shortlist.load(shortlist_path)
    if not shortlist.topics:
        raise PipelineError("Shortlist has no topics")

    already = existing_slugs(run_dir)
    pending_topics = [t for t in shortlist.topics if t.slug not in already]
    if not pending_topics:
        raise PipelineError(
            "All shortlist topics already have articles in this run; "
            "curate new topics first"
        )
    if len(pending_topics) < len(shortlist.topics):
        skipped = len(shortlist.topics) - len(pending_topics)
        print(f"Skipping {skipped} shortlist topic(s) that already have articles")

    state = load_or_create_state(run_dir, model or OPENROUTER_BELGIUM_MODEL)
    mark_stage(state, "write", status="running")

    call = writer_fn or agent_api.run_writer
    articles_dir = run_dir / "articles"
    articles_dir.mkdir(parents=True, exist_ok=True)

    articles: List[BelgiumArticle] = []
    usages: List[Dict[str, Any]] = []
    try:
        for i, topic in enumerate(pending_topics, start=1):
            print(
                f"Writing article {i}/{len(pending_topics)}: {topic.slug} "
                "(fresh model context)"
            )
            topic_shortlist = Shortlist(topics=[topic], notes=None)
            article, usage = _write_one_topic(
                run_dir=run_dir,
                topic_shortlist=topic_shortlist,
                model=model,
                writer_fn=call,
            )
            if article.slug in already:
                continue
            article.save(articles_dir / f"{article.slug}.json")
            article.save_markdown(articles_dir / f"{article.slug}.md")
            articles.append(article)
            usages.append(usage)
            already.add(article.slug)

        if not articles:
            raise PipelineError(
                "Writer produced no new articles (all slugs already existed)"
            )

        merged_usage = _merge_usage(usages)
        mark_stage(
            state,
            "write",
            status="ok",
            generation_id=merged_usage.get("generation_id"),
            detail=f"{len(articles)} articles ({len(usages)} isolated calls)",
            usage=merged_usage,
        )
        return articles
    except Exception as exc:
        mark_stage(state, "write", status="error", detail=str(exc))
        raise


def resolve_stages(
    *,
    stage: Optional[str] = None,
    from_stage: Optional[str] = None,
    to_stage: Optional[str] = None,
) -> Sequence[str]:
    """Resolve which pipeline stages to run."""
    if stage and (from_stage or to_stage):
        raise PipelineError("Do not combine --stage with --from-stage or --to-stage")
    if from_stage and to_stage:
        start = _require_stage(from_stage, flag="from-stage")
        end = _require_stage(to_stage, flag="to-stage")
        if end < start:
            raise PipelineError("--to-stage cannot come before --from-stage")
        return STAGES[start:end + 1]
    if stage:
        _require_stage(stage, flag="stage")
        return (stage,)
    if from_stage:
        return STAGES[_require_stage(from_stage, flag="from-stage"):]
    if to_stage:
        return STAGES[:_require_stage(to_stage, flag="to-stage") + 1]
    return STAGES


def _require_stage(name: str, *, flag: str) -> int:
    if name not in STAGES:
        raise PipelineError(f"Unknown {flag} {name!r}; choose from {STAGES}")
    return STAGES.index(name)


def run_pipeline(
    *,
    run_dir: Optional[Path] = None,
    days: int = DEFAULT_LOOKBACK_DAYS,
    max_topics: int = DEFAULT_MAX_TOPICS,
    stage: Optional[str] = None,
    from_stage: Optional[str] = None,
    to_stage: Optional[str] = None,
    model: Optional[str] = None,
    client: Optional[VrtClient] = None,
    curator_fn=None,
    writer_fn=None,
    fetch_bodies: bool = True,
) -> Path:
    """Execute the requested stages. Returns the run directory path."""
    to_run = resolve_stages(stage=stage, from_stage=from_stage, to_stage=to_stage)

    if run_dir is None:
        run_dir = new_run_dir()
    else:
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        _seed_run_dir(run_dir)

    for name in to_run:
        if name == "ingest":
            stage_ingest(
                run_dir,
                days=days,
                client=client,
                fetch_bodies=fetch_bodies,
                model=model,
            )
        elif name == "curate":
            stage_curate(
                run_dir,
                max_topics=max_topics,
                model=model,
                curator_fn=curator_fn,
            )
        elif name == "write":
            stage_write(
                run_dir,
                model=model,
                writer_fn=writer_fn,
            )

    return run_dir
