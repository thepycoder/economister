"""Structured logging to validate EPUB image-placement hypotheses."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from config import LOGS_DIR, PROJECT_ROOT

# H1: body scope too wide → related figures leak in
# H2: hero URL ≠ figure URL for same asset → duplicate
# H3: exact-URL seen set suppresses wrong sibling of near-dupe
# H4: fetch returned shell/paywall/teaser HTML
# H5: EPUB path/filename mismatch
# H6: leaked figures appear mid-article in DOM order


def asset_key(url: Optional[str]) -> Optional[str]:
    """Normalize CDN/image URL to a stable content-assets path key."""
    if not url:
        return None
    match = re.search(r'(/content-assets/[^\s?#"\']+)', url)
    if match:
        return match.group(1).rstrip('/')
    path = urlparse(url).path
    return path or url


class HypothesisLogger:
    """Append JSONL events for image-placement hypothesis validation."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or (PROJECT_ROOT / LOGS_DIR / 'image_hypotheses.jsonl')
        self.path.parent.mkdir(exist_ok=True, parents=True)
        self.path.write_text('')  # fresh run
        self._article_images: dict[str, list[dict[str, Any]]] = {}

    def log(self, event: str, **payload: Any) -> None:
        record = {
            'ts': datetime.now(timezone.utc).isoformat(),
            'event': event,
            **payload,
        }
        self.path.parent.mkdir(exist_ok=True, parents=True)
        with self.path.open('a', encoding='utf-8') as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + '\n')

    def article_start(self, url: str, title: Optional[str],
                      section: Optional[str]) -> None:
        self.log(
            'article_start',
            url=url,
            title=title,
            section=section,
        )
        self._article_images[url] = []

    def body_scope(
        self,
        url: str,
        selector: str,
        figures_in_body: int,
        figures_in_main: int,
        figures_outside_body: list[dict[str, Any]],
    ) -> None:
        """H1/H6: compare figures inside chosen body vs whole main."""
        leak_count = len(figures_outside_body)
        self.log(
            'body_scope',
            hypothesis=['H1', 'H6'],
            url=url,
            selector=selector,
            figures_in_body=figures_in_body,
            figures_in_main=figures_in_main,
            figures_outside_body_count=leak_count,
            figures_outside_body=figures_outside_body,
            h1_suspect=leak_count > 0 or selector in {
                'main#content', 'main[role=main]', 'soup'
            },
        )

    def hero_extracted(
        self,
        url: str,
        hero_url: Optional[str],
        source: Optional[str],
        accepted: bool,
        reason: Optional[str] = None,
    ) -> None:
        self.log(
            'hero_extracted',
            hypothesis=['H2'],
            url=url,
            hero_url=hero_url,
            hero_asset=asset_key(hero_url),
            source=source,
            accepted=accepted,
            reason=reason,
        )

    def figure_candidate(
        self,
        url: str,
        src: str,
        *,
        accepted: bool,
        reason: Optional[str],
        caption: Optional[str],
        parent_hint: Optional[str],
        inside_article_body: bool,
        block_index: int,
        paragraph_index_before: int,
        near_dupe_of: Optional[str] = None,
        exact_seen: bool = False,
    ) -> None:
        """H1/H2/H3/H6: every figure considered for an article."""
        key = asset_key(src)
        record = {
            'src': src,
            'asset': key,
            'accepted': accepted,
            'reason': reason,
            'caption': caption,
            'parent_hint': parent_hint,
            'inside_article_body': inside_article_body,
            'block_index': block_index,
            'paragraph_index_before': paragraph_index_before,
            'near_dupe_of': near_dupe_of,
            'exact_seen': exact_seen,
        }
        self._article_images.setdefault(url, []).append(record)
        self.log(
            'figure_candidate',
            hypothesis=['H1', 'H2', 'H3', 'H6'],
            url=url,
            **record,
            h1_suspect=accepted and not inside_article_body,
            h2_suspect=bool(near_dupe_of) and accepted,
            h3_suspect=exact_seen and bool(near_dupe_of),
            h6_suspect=accepted and paragraph_index_before > 0
            and not inside_article_body,
        )

    def fetch_quality(self, url: str, html: str) -> None:
        """H4: detect shell / paywall / teaser pages."""
        lower = html[:20000].lower()
        markers = {
            'paywall': any(m in lower for m in (
                'already have an account?',
                'continue with a free trial',
                'create account to unlock',
            )),
            'teaser_more_from': 'more from' in lower,
            'has_article_body': (
                'data-component="article-body"' in lower
                or 'itemprop="articlebody"' in lower
            ),
            'has_h1': '<h1' in lower,
            'html_length': len(html),
        }
        self.log(
            'fetch_quality',
            hypothesis=['H4'],
            url=url,
            **markers,
            h4_suspect=markers['paywall'] or not markers['has_article_body'],
        )

    def article_summary(self, url: str, title: Optional[str],
                        image_count: int, paragraph_count: int) -> None:
        images = self._article_images.get(url, [])
        accepted = [i for i in images if i.get('accepted')]
        assets = [i.get('asset') for i in accepted if i.get('asset')]
        dupe_assets = sorted({a for a in assets if assets.count(a) > 1})
        outside = [i for i in accepted if not i.get('inside_article_body')]
        self.log(
            'article_summary',
            hypothesis=['H1', 'H2', 'H6'],
            url=url,
            title=title,
            paragraph_count=paragraph_count,
            image_count=image_count,
            accepted_images=accepted,
            duplicate_assets_in_article=dupe_assets,
            accepted_outside_body=len(outside),
            h1_suspect=len(outside) > 0,
            h2_suspect=len(dupe_assets) > 0,
        )

    def epub_image_added(
        self,
        article_url: str,
        article_title: Optional[str],
        chapter_file: str,
        src_url: str,
        epub_filename: str,
        block_index: int,
        is_hero: bool,
    ) -> None:
        """H5: record chapter HTML ↔ EPUB item mapping."""
        self.log(
            'epub_image_added',
            hypothesis=['H5'],
            article_url=article_url,
            article_title=article_title,
            chapter_file=chapter_file,
            src_url=src_url,
            src_asset=asset_key(src_url),
            epub_filename=epub_filename,
            html_src=f'images/{epub_filename}',
            block_index=block_index,
            is_hero=is_hero,
        )

    def near_dupe_lookup(
        self, url: str, seen_urls: set[str]
    ) -> Optional[str]:
        """Return a previously seen URL sharing the same asset key."""
        key = asset_key(url)
        if not key:
            return None
        for seen in seen_urls:
            if asset_key(seen) == key and seen != url:
                return seen
        return None


# Process-wide logger used by extractor / builder
PROBE = HypothesisLogger()
