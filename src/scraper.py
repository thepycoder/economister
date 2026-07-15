"""Main scraper orchestrator for The Economist."""

import time
from typing import List, Optional

import requests
from requests.cookies import create_cookie

from config import (
    ARTICLE_FETCH_COOLDOWN,
    ECONOMIST_URL,
    USER_AGENT,
)
from models import Article, Edition
from utils import (
    extract_date_from_cover_url, extract_date_from_text,
    has_extractable_content, save_debug_html,
)
from browser import BrowserManager
from content_extractor import ContentExtractor


class EconomistScraper:
    """Orchestrates scraping of The Economist website."""

    def __init__(self, debug: bool = False):
        """Initialize the scraper.

        Args:
            debug: Enable debug mode.
        """
        self.debug = debug
        self.browser = BrowserManager()
        self.extractor = ContentExtractor(debug=debug)
        self.edition = Edition()
        self.session: Optional[requests.Session] = None

    def initialize(self) -> None:
        """Initialize browser, authenticate, and switch to HTTP session."""
        self.browser.setup()
        self.browser.login()
        self._refresh_session()
        self.browser.quit()
        print("Using authenticated HTTP session for scraping")

    def _refresh_session(self) -> None:
        """Export browser cookies into a requests session."""
        self.session = self.browser.export_requests_session()

    def _recover_session(self) -> bool:
        """Restart browser login after session or tab failure."""
        print("  Recovering authenticated session...")
        try:
            self.browser.setup()
            self.browser.login()
            self._refresh_session()
            self.browser.quit()
            return True
        except Exception as exc:
            print(f"  Session recovery failed: {exc}")
            return False

    def _is_auth_failure(self, response: requests.Response) -> bool:
        """Return True when the response indicates an expired login."""
        if response.status_code in (401, 403):
            return True

        final_url = response.url.lower()
        if "/api/auth/login" in final_url or "myaccount.economist.com" in final_url:
            return True

        snippet = response.text[:8000].lower()
        paywall_markers = (
            "already have an account?",
            "continue with a free trial",
            "create account to unlock",
            "get full access to our independent journalism",
        )
        return any(marker in snippet for marker in paywall_markers)

    def _fetch_page(self, url: str, wait_time: int = 0) -> str:
        """Fetch a page using the authenticated HTTP session."""
        if not self.session:
            self._recover_session()

        headers = {"User-Agent": USER_AGENT}
        recovered = False
        last_response: Optional[requests.Response] = None

        for attempt in range(4):
            try:
                response = self.session.get(url, timeout=30, headers=headers)
            except (requests.Timeout, requests.ConnectionError):
                if attempt < 3:
                    time.sleep(min(2 ** attempt, 8))
                    continue
                raise

            last_response = response

            if response.status_code in (429, 502, 503, 504) and attempt < 3:
                time.sleep(min(2 ** attempt, 8))
                continue

            if self._is_auth_failure(response):
                if not recovered and self._recover_session():
                    recovered = True
                    continue
                response.raise_for_status()

            response.raise_for_status()
            if wait_time:
                time.sleep(wait_time)
            return response.text

        if last_response is not None:
            last_response.raise_for_status()
        raise requests.RequestException(f"Failed to fetch {url}")

    def scrape_weekly_edition(self) -> Edition:
        """Scrape the weekly edition page for article links.

        Returns:
            Edition object with article metadata.
        """
        print("Getting article URLs...")
        html = self._fetch_page(ECONOMIST_URL)
        save_debug_html("weekly_edition", html, self.debug)

        # Extract edition date
        self._extract_edition_date(html)

        # Extract cover URL
        cover_url = self.extractor.extract_cover_url(html)
        if cover_url:
            self.edition.cover_url = cover_url
            if self.debug:
                print(f"Found cover: {cover_url}")

        # Extract article links (WTW merged explicitly for short TOC labels)
        article_links = self.extractor.extract_article_links(html)
        wtw_links = self.extractor.extract_world_this_week_links(html)
        article_links = self.extractor.merge_article_links(
            article_links, wtw_links
        )
        article_links = self._sort_edition_articles(article_links)

        print(f"Found {len(article_links)} unique articles")

        # Create Article objects with metadata
        for link_info in article_links:
            article = Article(
                title=link_info['title'],
                url=link_info['url'],
                section=link_info['section']
            )
            self.edition.articles.append(article)

        self._print_section_counts()

        return self.edition

    def scrape_article(self, article: Article) -> bool:
        """Scrape full content for an article.

        Args:
            article: Article object to populate with content.

        Returns:
            True if article was successfully scraped.
        """
        if not article.url:
            return False

        try:
            html = self._fetch_page(article.url)
            save_debug_html(article.title or "article", html, self.debug)

            # Extract content into the same article object
            extracted = self.extractor.extract_article(html, article.url)

            # Update article with extracted content
            if not article.title:
                article.title = extracted.title
            article.subtitle = extracted.subtitle
            article.content_blocks = extracted.content_blocks

            if not has_extractable_content(article):
                print("  ⚠ Skipped (no text or images found)")
                return False

            print(f"  ✓ Extracted {article.paragraph_count} paragraphs, "
                  f"{article.image_count} images")
            return True

        except Exception as e:
            print(f"  ✗ Error: {e}")
            return False

    def scrape_articles(self, limit: Optional[int] = None) -> List[Article]:
        """Scrape multiple articles with optional limit.

        Args:
            limit: Maximum number of articles to scrape.

        Returns:
            List of successfully scraped articles.
        """
        articles = self.edition.articles

        if limit and limit > 0:
            original_count = len(articles)
            articles = articles[:limit]
            print(f"\n📎 Limiting to {len(articles)} articles "
                  f"(out of {original_count} available)")

        successful_articles = []

        for i, article in enumerate(articles, 1):
            section = article.section or "Unknown"
            title = (article.title or "Untitled")[:50]
            print(f"\n[{i}/{len(articles)}] [{section}] {title}...")

            if self.scrape_article(article):
                successful_articles.append(article)

            if i < len(articles):
                time.sleep(ARTICLE_FETCH_COOLDOWN)

        return successful_articles

    def cleanup(self) -> None:
        """Clean up resources."""
        self.browser.quit()

    def _extract_edition_date(self, html: str) -> None:
        """Extract and set the edition date from the page."""
        # Try to find date from cover image
        cover_url = self.extractor.extract_cover_url(html)
        if cover_url:
            date = extract_date_from_cover_url(cover_url)
            if date:
                self.edition.date = date
                print(f"Weekly edition date: {date}")

                # Track cover pattern
                import re
                match = re.search(r'/(\d{8})_', cover_url)
                if match:
                    self.extractor.cover_patterns.add(match.group(1))
                    print(f"Tracking cover pattern: {match.group(1)}")

                return

        # Fallback: find date from page text
        date = extract_date_from_text(html)
        if date:
            self.edition.date = date
            print(f"Weekly edition date: {date}")

    def _sort_edition_articles(self, article_links: List[dict]) -> List[dict]:
        """Order articles by section, with WTW subsections Politics → Business → Cartoon."""
        from config import SECTION_ORDER
        from utils import wtw_subsection_sort_key

        section_rank = {name: i for i, name in enumerate(SECTION_ORDER)}

        def sort_key(link: dict) -> tuple:
            section = link.get('section') or 'Other'
            section_index = section_rank.get(section, len(SECTION_ORDER))
            wtw_index = (
                wtw_subsection_sort_key(link.get('url', ''))
                if section == 'The world this week' else 0
            )
            return (section_index, wtw_index, link.get('title') or '')

        return sorted(article_links, key=sort_key)

    def _print_section_counts(self) -> None:
        """Print article counts by section."""
        from config import SECTION_ORDER

        sections = self.edition.articles_by_section()

        print("\nArticles by section:")
        for section in SECTION_ORDER:
            if section in sections:
                print(f"  {section}: {len(sections[section])}")

        if 'Other' in sections:
            print(f"  Other: {len(sections['Other'])}")
            if self.debug:
                print("\n  Uncategorized articles:")
                for article in sections['Other']:
                    if article.url:
                        url_part = article.url.split('/')[-3]
                        title = (article.title or "")[:50]
                        print(f"    - {title}... [{url_part}]")
