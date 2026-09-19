"""Data models for the Belgium news pipeline."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class SourceArticle:
    """A VRT NWS article captured during ingest."""

    title: str
    url: str
    published: Optional[str] = None
    category: Optional[str] = None
    summary: Optional[str] = None
    body: Optional[str] = None
    slug: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SourceArticle":
        """Deserialize from a plain dict."""
        return cls(
            title=str(data.get("title") or ""),
            url=str(data.get("url") or ""),
            published=data.get("published"),
            category=data.get("category"),
            summary=data.get("summary"),
            body=data.get("body"),
            slug=data.get("slug"),
        )


@dataclass
class SourceIndex:
    """Index of ingested VRT articles for one pipeline run."""

    fetched_at: str
    days: int
    articles: List[SourceArticle] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "fetched_at": self.fetched_at,
            "days": self.days,
            "articles": [a.to_dict() for a in self.articles],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SourceIndex":
        """Deserialize from a plain dict."""
        return cls(
            fetched_at=str(data.get("fetched_at") or ""),
            days=int(data.get("days") or 0),
            articles=[
                SourceArticle.from_dict(item)
                for item in (data.get("articles") or [])
            ],
        )

    def save(self, path: Path) -> None:
        """Write index JSON to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> "SourceIndex":
        """Load index JSON from disk."""
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


@dataclass
class TopicCandidate:
    """One Economist-worthy Belgium topic from the curator."""

    slug: str
    working_hed: str
    why_economist: str
    source_urls: List[str] = field(default_factory=list)
    confidence: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TopicCandidate":
        """Deserialize from a plain dict."""
        return cls(
            slug=_slugify(str(data.get("slug") or data.get("working_hed") or "topic")),
            working_hed=str(data.get("working_hed") or ""),
            why_economist=str(data.get("why_economist") or ""),
            source_urls=[str(u) for u in (data.get("source_urls") or [])],
            confidence=float(data.get("confidence") or 0.5),
        )


@dataclass
class Shortlist:
    """Curator output: 1–5 selected topics."""

    topics: List[TopicCandidate] = field(default_factory=list)
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "topics": [t.to_dict() for t in self.topics],
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Shortlist":
        """Deserialize from a plain dict."""
        raw_topics = data.get("topics")
        if raw_topics is None and isinstance(data.get("shortlist"), list):
            raw_topics = data["shortlist"]
        return cls(
            topics=[TopicCandidate.from_dict(t) for t in (raw_topics or [])],
            notes=data.get("notes"),
        )

    def save(self, path: Path) -> None:
        """Write shortlist JSON to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> "Shortlist":
        """Load shortlist JSON from disk."""
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


@dataclass
class ArticleSource:
    """A cited source for a generated Belgium article."""

    title: str
    url: str
    publisher: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArticleSource":
        """Deserialize from a plain dict."""
        return cls(
            title=str(data.get("title") or ""),
            url=str(data.get("url") or ""),
            publisher=data.get("publisher"),
        )


@dataclass
class BelgiumArticle:
    """AI-generated Belgium section article (EPUB-compatible fields)."""

    title: str
    subtitle: Optional[str] = None
    slug: str = ""
    section: str = "Belgium"
    paragraphs: List[str] = field(default_factory=list)
    sources: List[ArticleSource] = field(default_factory=list)
    topic_rationale: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "slug": self.slug,
            "section": self.section,
            "paragraphs": list(self.paragraphs),
            "sources": [s.to_dict() for s in self.sources],
            "topic_rationale": self.topic_rationale,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BelgiumArticle":
        """Deserialize from a plain dict."""
        slug = str(data.get("slug") or "")
        title = str(data.get("title") or "")
        if not slug:
            slug = _slugify(title or "article")
        return cls(
            title=title,
            subtitle=data.get("subtitle"),
            slug=slug,
            section=str(data.get("section") or "Belgium"),
            paragraphs=[str(p) for p in (data.get("paragraphs") or []) if str(p).strip()],
            sources=[
                ArticleSource.from_dict(s) for s in (data.get("sources") or [])
            ],
            topic_rationale=data.get("topic_rationale"),
        )

    def save(self, path: Path) -> None:
        """Write article JSON to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def to_markdown(self) -> str:
        """Render a proofreading-friendly markdown document."""
        lines: List[str] = [f"# {self.title}", ""]
        if self.subtitle:
            lines.append(f"*{self.subtitle}*")
            lines.append("")
        for paragraph in self.paragraphs:
            lines.append(paragraph)
            lines.append("")
        if self.sources:
            lines.append("---")
            lines.append("")
            lines.append("## Sources")
            lines.append("")
            for i, source in enumerate(self.sources, 1):
                publisher = f" — {source.publisher}" if source.publisher else ""
                lines.append(f"{i}. [{source.title}]({source.url}){publisher}")
            lines.append("")
        if self.topic_rationale:
            lines.append("---")
            lines.append("")
            lines.append(f"*Rationale: {self.topic_rationale}*")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def save_markdown(self, path: Path) -> None:
        """Write the markdown proof next to the JSON article."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_markdown(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "BelgiumArticle":
        """Load article JSON from disk."""
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


@dataclass
class RunState:
    """Persisted status for a pipeline run directory."""

    run_dir: str
    created_at: str
    model: str = ""
    stages: Dict[str, Any] = field(default_factory=dict)
    cost: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunState":
        """Deserialize from a plain dict."""
        return cls(
            run_dir=str(data.get("run_dir") or ""),
            created_at=str(data.get("created_at") or ""),
            model=str(data.get("model") or ""),
            stages=dict(data.get("stages") or {}),
            cost=dict(data.get("cost") or {}),
        )

    def save(self, path: Path) -> None:
        """Write run state JSON to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> "RunState":
        """Load run state JSON from disk."""
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _slugify(text: str, max_length: int = 60) -> str:
    """Create a URL-safe slug from text."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    return (text or "topic")[:max_length]


def validate_shortlist(data: Dict[str, Any], max_topics: int = 5) -> List[str]:
    """Return validation errors for a shortlist payload, or empty if valid."""
    errors: List[str] = []
    try:
        shortlist = Shortlist.from_dict(data)
    except (TypeError, ValueError, KeyError) as exc:
        return [f"invalid shortlist shape: {exc}"]

    if not shortlist.topics:
        errors.append("shortlist must contain at least one topic")
    if len(shortlist.topics) > max_topics:
        errors.append(f"shortlist has {len(shortlist.topics)} topics; max is {max_topics}")

    for i, topic in enumerate(shortlist.topics):
        if not topic.slug:
            errors.append(f"topics[{i}].slug is required")
        if not topic.working_hed:
            errors.append(f"topics[{i}].working_hed is required")
        if not topic.why_economist:
            errors.append(f"topics[{i}].why_economist is required")
        if not topic.source_urls:
            errors.append(f"topics[{i}].source_urls must be non-empty")
        if not (0.0 <= topic.confidence <= 1.0):
            errors.append(f"topics[{i}].confidence must be between 0 and 1")
    return errors


def validate_article(data: Dict[str, Any]) -> List[str]:
    """Return validation errors for an article payload, or empty if valid."""
    errors: List[str] = []
    try:
        article = BelgiumArticle.from_dict(data)
    except (TypeError, ValueError, KeyError) as exc:
        return [f"invalid article shape: {exc}"]

    if not article.title:
        errors.append("title is required")
    if not article.slug:
        errors.append("slug is required")
    if article.section != "Belgium":
        errors.append('section must be "Belgium"')
    if len(article.paragraphs) < 3:
        errors.append("paragraphs must contain at least 3 items")
    word_count = sum(len(p.split()) for p in article.paragraphs)
    if word_count < 200:
        errors.append(f"article is too short ({word_count} words); expected ~600–900")
    if not article.sources:
        errors.append("sources must be non-empty")
    for i, source in enumerate(article.sources):
        if not source.url:
            errors.append(f"sources[{i}].url is required")
        if not source.title:
            errors.append(f"sources[{i}].title is required")
    if not article.topic_rationale:
        errors.append("topic_rationale is required")
    return errors


def utc_now_iso() -> str:
    """Return current UTC time as an ISO-8601 string."""
    from datetime import timezone

    return (
        datetime.now(tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
