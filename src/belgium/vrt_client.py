"""VRT NWS client: BFF listing + article body extraction.

Talks to the public backend-for-frontend at ``vrtnws-web-bff.vrt.be``
(same surface documented by vrtnws_mcp). No authentication required.
"""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Set
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from belgium.config import (
    DEFAULT_LOOKBACK_DAYS,
    PREFERRED_CATEGORIES,
    SKIP_CATEGORIES,
)
from belgium.models import SourceArticle, SourceIndex, utc_now_iso

BFF_BASE = "https://vrtnws-web-bff.vrt.be/vrtnws-bff/web"
SITE_BASE = "https://www.vrt.be/vrtnws"
DEFAULT_LANGUAGE = "nl"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 "
    "economister-belgium/0.1"
)

TEASER_TYPES = {
    "articleTeaser",
    "mediaTeaser",
    "searchTeaser",
    "showcaseTeaser",
    "verticalTeaser",
    "horizontalTeaser",
    "highlightTeaser",
    "articleInternalTeaser",
    "listItem",
    "textTeaser",
}
CHILD_KEYS = ("compositions", "items", "tabs", "children")

KNOWN_CATEGORIES = {
    "binnenland": "Binnenland",
    "buitenland": "Buitenland",
    "milieu-en-klimaat": "Milieu & Klimaat",
    "cultuur-en-media": "Cultuur & Media",
    "technologie-en-wetenschap": "Technologie & Wetenschap",
    "religie-en-levensbeschouwing": "Religie & Levensbeschouwing",
    "royalty": "Royalty",
    "sport": "Sport",
    "analyse": "Analyse",
    "check": "Check",
    "winwin": "WinWin",
    "nws-ombudsvrouw": "NWS Ombudsvrouw",
}


class VrtNwsError(RuntimeError):
    """Raised when the VRT NWS backend cannot serve a request."""


def _b64url(value: str) -> str:
    """Base64url-encode without padding."""
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def html_to_text(html: Optional[str]) -> str:
    """Flatten an HTML fragment to plain text, keeping paragraph breaks."""
    if not html:
        return ""
    if "<" not in html:
        return html.strip()
    soup = BeautifulSoup(html, "lxml")
    parts: List[str] = []
    for node in soup.find_all(["p", "li", "h1", "h2", "h3", "h4", "blockquote"]):
        text = node.get_text(" ", strip=True)
        if text:
            parts.append(text)
    if not parts:
        text = soup.get_text(" ", strip=True)
        parts = [text] if text else []
    joined = "\n\n".join(parts)
    return re.sub(r"[ \t\xa0]+", " ", joined).strip()


def _text_of(node: Any) -> Optional[str]:
    """Read VRT's ``{"text": ...}`` / ``{"html": ...}`` label shape."""
    if isinstance(node, str):
        return node.strip() or None
    if not isinstance(node, dict):
        return None
    if node.get("text"):
        return str(node["text"]).strip() or None
    if node.get("html"):
        return html_to_text(node["html"]) or None
    return None


def _first_uri(node: Dict[str, Any]) -> Optional[str]:
    """Find the NAVIGATE target of a teaser."""
    action = node.get("action")
    if isinstance(action, dict) and action.get("uri"):
        return str(action["uri"])
    for candidate in node.get("actions") or []:
        if isinstance(candidate, dict) and candidate.get("uri"):
            return str(candidate["uri"])
    return None


def _timestamp_ms(node: Dict[str, Any]) -> Optional[int]:
    """Extract a millisecond epoch from a teaser or heading node."""
    publication = node.get("publication")
    if isinstance(publication, dict) and publication.get("timestamp"):
        return int(publication["timestamp"])
    for meta in node.get("metadata") or []:
        if isinstance(meta, dict) and meta.get("type") == "time" and meta.get("timestamp"):
            return int(meta["timestamp"])
    return None


def ms_to_iso(timestamp_ms: Optional[int]) -> Optional[str]:
    """Convert a millisecond epoch to an ISO-8601 UTC string."""
    if timestamp_ms is None:
        return None
    # VRT sometimes returns seconds; treat small values as seconds.
    seconds = timestamp_ms / 1000.0 if timestamp_ms > 10_000_000_000 else float(timestamp_ms)
    dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def iter_nodes(node: Any) -> Iterator[Dict[str, Any]]:
    """Depth-first walk over every dict in a composition tree."""
    if isinstance(node, list):
        for child in node:
            yield from iter_nodes(child)
        return
    if not isinstance(node, dict):
        return
    yield node
    for key in CHILD_KEYS:
        child = node.get(key)
        if child:
            yield from iter_nodes(child)


def normalise_article_url(url_or_path: str, language: str = DEFAULT_LANGUAGE) -> str:
    """Accept a full URL or path and return a canonical https URL with trailing slash."""
    value = url_or_path.strip()
    if value.startswith("//"):
        value = "https:" + value
    if value.startswith("http://"):
        value = "https://" + value[len("http://"):]
    if value.startswith("https://"):
        if "vrt.be" not in value:
            raise VrtNwsError(f"Not a vrt.be URL: {url_or_path}")
        return value if value.endswith("/") else value + "/"
    value = "/" + value.lstrip("/")
    if not value.startswith("/vrtnws/"):
        value = f"/vrtnws/{language}{value}"
    if not value.endswith("/"):
        value += "/"
    return "https://www.vrt.be" + value


def extract_summaries(payload: Any) -> List[Dict[str, Any]]:
    """Collect teaser nodes as summary dicts, de-duplicated, document order."""
    seen: Set[str] = set()
    out: List[Dict[str, Any]] = []
    for node in iter_nodes(payload):
        if node.get("type") not in TEASER_TYPES:
            continue
        title = _text_of(node.get("title"))
        url = _first_uri(node)
        if not title or not url or "/vrtnws/" not in url:
            continue
        if url in seen:
            continue
        # Skip pure media destinations for the Belgium briefing pack.
        if any(part in url for part in ("/kijk/", "/luister/", "/liveblog/")):
            continue
        seen.add(url)
        tag = node.get("tag") if isinstance(node.get("tag"), dict) else {}
        out.append({
            "title": title,
            "url": url if url.endswith("/") else url + "/",
            "summary": _text_of(node.get("subtitle")) or _text_of(node.get("description")),
            "published": ms_to_iso(_timestamp_ms(node)),
            "category": _text_of(tag) or _text_of(node.get("label")),
        })
    return out


def parse_article(payload: Dict[str, Any], url: str) -> SourceArticle:
    """Build a SourceArticle from a ``page/content`` payload."""
    heading: Dict[str, Any] = {}
    for node in iter_nodes(payload):
        if node.get("type") == "articleHeading":
            heading = node
            break

    title = _text_of(heading.get("title")) or ""
    if not title:
        properties = payload.get("pageProperties") or {}
        title = (
            (properties.get("seo") or {}).get("title")
            or (properties.get("analytics") or {}).get("title")
            or ""
        )

    body_nodes: List[Dict[str, Any]] = []
    for node in iter_nodes(payload):
        if node.get("type") == "articleMain":
            body_nodes = list(node.get("compositions") or [])
            break
    if not body_nodes:
        body_nodes = [
            n for n in iter_nodes(payload)
            if str(n.get("type") or "").startswith("article")
        ]

    paragraphs: List[str] = []
    for node in body_nodes:
        node_type = node.get("type")
        if node_type == "articleText":
            text = html_to_text((node.get("text") or {}).get("html"))
            if text:
                paragraphs.append(text)
        elif node_type in {"articleTitle", "articleSubtitle"}:
            text = _text_of(node.get("title"))
            if text:
                paragraphs.append(text)
        elif node_type in {"articleQuote", "quote"}:
            text = _text_of(node.get("text")) or _text_of(node.get("title"))
            if text:
                paragraphs.append(text)

    tags: List[str] = []
    for node in iter_nodes(payload):
        if node.get("type") == "detailMoreItem":
            label = _text_of(node.get("title"))
            if label and label not in tags:
                tags.append(label)

    slug = url.rstrip("/").split("/")[-1]
    return SourceArticle(
        title=title,
        url=url,
        published=ms_to_iso(_timestamp_ms(heading)),
        category=tags[0] if tags else None,
        summary=_text_of(heading.get("subtitle")),
        body="\n\n".join(paragraphs) if paragraphs else None,
        slug=slug,
    )


class VrtClient:
    """Synchronous VRT NWS BFF client."""

    def __init__(
        self,
        *,
        language: str = DEFAULT_LANGUAGE,
        timeout: float = 30.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.language = language
        self.timeout = timeout
        self._session = session or requests.Session()
        self._session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        })

    def _get_json(self, url: str) -> Dict[str, Any]:
        try:
            response = self._session.get(url, timeout=self.timeout)
        except requests.RequestException as exc:
            raise VrtNwsError(f"Request to VRT NWS failed: {exc}") from exc
        if response.status_code == 404:
            raise VrtNwsError(f"VRT NWS returned 404 for {url}")
        if response.status_code >= 400:
            raise VrtNwsError(
                f"VRT NWS returned HTTP {response.status_code} for {url}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise VrtNwsError(f"VRT NWS returned non-JSON for {url}") from exc

    def get_page(self, page_url: str) -> Dict[str, Any]:
        """Fetch any vrt.be/vrtnws page as composition JSON."""
        return self._get_json(f"{BFF_BASE}/page/content/{_b64url(page_url)}")

    def get_latest(self) -> Dict[str, Any]:
        """The Net binnen feed."""
        return self.get_page(f"{SITE_BASE}/{self.language}/net-binnen/")

    def get_section_page(self, slug: str) -> Dict[str, Any]:
        """The ``/rubrieken/<slug>/`` page."""
        return self.get_page(
            f"{SITE_BASE}/{self.language}/rubrieken/{quote(slug.strip('/'))}/"
        )

    def read_article(self, url: str) -> SourceArticle:
        """Fetch one article and return title + body text."""
        canonical = normalise_article_url(url, self.language)
        payload = self.get_page(canonical)
        article = parse_article(payload, canonical)
        if not article.title:
            raise VrtNwsError(f"No article found at {canonical}")
        return article


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _category_allowed(category: Optional[str], skip: Iterable[str]) -> bool:
    if not category:
        return True
    label = category.strip().lower()
    skip_set = {s.lower() for s in skip}
    for slug, title in KNOWN_CATEGORIES.items():
        if slug in skip_set or title.lower() in skip_set:
            if slug in label or title.lower() in label:
                return False
    return True


def collect_week(
    *,
    days: int = DEFAULT_LOOKBACK_DAYS,
    categories: Optional[Iterable[str]] = None,
    client: Optional[VrtClient] = None,
    fetch_bodies: bool = True,
    max_articles: int = 80,
) -> SourceIndex:
    """Ingest recent VRT articles into a SourceIndex.

    Pulls Net binnen plus preferred section pages, filters by date and
    category, then optionally fetches full article bodies.
    """
    client = client or VrtClient()
    cats = list(categories) if categories is not None else list(PREFERRED_CATEGORIES)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=max(1, days))

    seen: Set[str] = set()
    summaries: List[Dict[str, Any]] = []

    payloads: List[Dict[str, Any]] = []
    try:
        payloads.append(client.get_latest())
    except VrtNwsError:
        pass

    for slug in cats:
        if slug in SKIP_CATEGORIES:
            continue
        try:
            payloads.append(client.get_section_page(slug))
        except VrtNwsError:
            continue

    if not payloads:
        raise VrtNwsError("No VRT listings could be fetched")

    for payload in payloads:
        for item in extract_summaries(payload):
            url = item["url"]
            if url in seen:
                continue
            if not _category_allowed(item.get("category"), SKIP_CATEGORIES):
                continue
            published = _parse_iso(item.get("published"))
            if published is not None and published < cutoff:
                continue
            seen.add(url)
            summaries.append(item)

    summaries.sort(
        key=lambda i: _parse_iso(i.get("published")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    summaries = summaries[:max_articles]

    articles: List[SourceArticle] = []
    for item in summaries:
        if fetch_bodies:
            try:
                article = client.read_article(item["url"])
                # Prefer listing metadata when article page omits it.
                if not article.published:
                    article.published = item.get("published")
                if not article.category:
                    article.category = item.get("category")
                if not article.summary:
                    article.summary = item.get("summary")
                articles.append(article)
                continue
            except VrtNwsError:
                pass
        articles.append(SourceArticle(
            title=item["title"],
            url=item["url"],
            published=item.get("published"),
            category=item.get("category"),
            summary=item.get("summary"),
            body=None,
            slug=item["url"].rstrip("/").split("/")[-1],
        ))

    if not articles:
        raise VrtNwsError(
            f"No VRT articles found in the last {days} day(s) "
            f"for categories {cats}"
        )

    return SourceIndex(
        fetched_at=utc_now_iso(),
        days=days,
        articles=articles,
    )


def write_source_pack(index: SourceIndex, run_dir: Path) -> Path:
    """Write ``sources/index.json`` and per-article markdown files."""
    sources_dir = run_dir / "sources"
    articles_dir = sources_dir / "articles"
    articles_dir.mkdir(parents=True, exist_ok=True)

    for article in index.articles:
        slug = article.slug or article.url.rstrip("/").split("/")[-1]
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", slug)[:80] or "article"
        path = articles_dir / f"{safe}.md"
        lines = [
            f"# {article.title}",
            "",
            f"- URL: {article.url}",
            f"- Published: {article.published or 'unknown'}",
            f"- Category: {article.category or 'unknown'}",
            "",
        ]
        if article.summary:
            lines.extend([article.summary, ""])
        if article.body:
            lines.append(article.body)
        else:
            lines.append("_(body not fetched)_")
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    index_path = sources_dir / "index.json"
    index.save(index_path)
    return index_path
