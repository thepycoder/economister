"""Optional Belgium briefing for the weekly Economist EPUB."""

from __future__ import annotations

import html
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Optional

from belgium.config import BELGIUM_RUNS_DIR, OPENROUTER_API_KEY
from belgium.models import BelgiumArticle, Shortlist
from belgium.pipeline import load_existing_articles, run_pipeline, stage_write

# Thursday: digital edition lands and the NAS job runs. A Saturday retry
# should reuse that briefing; next Thursday must not.
EDITION_WEEKDAY = 3


def list_run_dirs(base: Optional[Path] = None) -> List[Path]:
    """Newest-first Belgium run directories."""
    root = base or BELGIUM_RUNS_DIR
    if not root.exists():
        return []
    return sorted(
        (path for path in root.iterdir() if path.is_dir()),
        key=lambda path: path.name,
        reverse=True,
    )


def latest_run_dir(base: Optional[Path] = None) -> Optional[Path]:
    """Return the newest run directory, if any."""
    runs = list_run_dirs(base)
    return runs[0] if runs else None


def briefing_window_start(now: Optional[datetime] = None) -> datetime:
    """Start of this edition week: Thursday 00:00 UTC."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    days_since_thursday = (current.weekday() - EDITION_WEEKDAY) % 7
    start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    return start - timedelta(days=days_since_thursday)


def run_is_fresh(run_dir: Path, *, now: Optional[datetime] = None) -> bool:
    """True when the run was created in the current Thursday edition week."""
    created = None
    state_path = run_dir / "run.json"
    if state_path.exists():
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict):
            created = data.get("created_at")
    if not created:
        created = run_dir.name[:10]
    try:
        stamp = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
    except ValueError:
        return False
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp >= briefing_window_start(now)


def to_epub_article(piece: BelgiumArticle) -> Any:
    """Convert a Belgium briefing article into an EPUB ``Article``."""
    from models import Article

    url = piece.sources[0].url if piece.sources else None
    article = Article(
        title=piece.title,
        subtitle=piece.subtitle,
        url=url,
        section="Belgium",
    )
    for paragraph in piece.paragraphs:
        article.add_paragraph(html.escape(paragraph))
    if piece.sources:
        lines = []
        for i, source in enumerate(piece.sources, 1):
            title = html.escape(source.title or source.url)
            href = html.escape(source.url, quote=True)
            extra = ""
            if source.publisher:
                extra = f" — {html.escape(source.publisher)}"
            lines.append(f'{i}. <a href="{href}">{title}</a>{extra}')
        article.add_paragraph("<em>Sources</em><br/>" + "<br/>".join(lines))
    return article


def shortlist_is_written(run_dir: Path) -> bool:
    """True when every shortlist topic already has an article file."""
    shortlist_path = run_dir / "shortlist.json"
    existing = {article.slug for article in load_existing_articles(run_dir)}
    if not shortlist_path.exists():
        return bool(existing)
    topics = Shortlist.load(shortlist_path).topics
    return bool(topics) and all(topic.slug in existing for topic in topics)


def collect_belgium_epub_articles(
    *,
    generate: bool = True,
    run_dir: Optional[Path] = None,
    writer_fn=None,
    curator_fn=None,
) -> List[Any]:
    """Load this week's Belgium pieces, generating them only if needed."""
    chosen = Path(run_dir) if run_dir is not None else latest_run_dir()
    if chosen is not None and run_dir is None and not run_is_fresh(chosen):
        print(
            f"Belgium section: {chosen.name} is from a previous edition week; "
            "generating a new briefing"
        )
        chosen = None

    if chosen is not None and shortlist_is_written(chosen):
        print(f"Belgium section: reusing {chosen.name}")
        return [to_epub_article(article) for article in load_existing_articles(chosen)]

    if not generate:
        if chosen is None:
            return []
        return [to_epub_article(article) for article in load_existing_articles(chosen)]

    if not OPENROUTER_API_KEY:
        print("Belgium section: OPENROUTER_API_KEY is unset; skipping generation")
        if chosen is None:
            return []
        return [to_epub_article(article) for article in load_existing_articles(chosen)]

    if chosen is not None and (chosen / "shortlist.json").exists():
        stage_write(chosen, writer_fn=writer_fn)
    else:
        chosen = run_pipeline(curator_fn=curator_fn, writer_fn=writer_fn)
    return [to_epub_article(article) for article in load_existing_articles(chosen)]


def try_attach_belgium_articles(
    articles: List[Any],
    *,
    enabled: bool = True,
    generate: bool = True,
    run_dir: Optional[Path] = None,
    writer_fn=None,
    curator_fn=None,
) -> List[Any]:
    """Append Belgium articles when possible. Never raise to the caller."""
    if not enabled:
        print("Belgium section disabled")
        return articles
    try:
        extra = collect_belgium_epub_articles(
            generate=generate,
            run_dir=run_dir,
            writer_fn=writer_fn,
            curator_fn=curator_fn,
        )
    except Exception as exc:
        print(f"\n⚠ Belgium section skipped: {exc}")
        return articles
    if not extra:
        print("\nBelgium section: no articles to add")
        return articles
    print(f"\nAdding Belgium section ({len(extra)} article(s))")
    articles.extend(extra)
    return articles
