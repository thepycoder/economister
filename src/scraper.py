"""Main scraper orchestrator for The Economist."""

import time
from typing import List, Optional

from selenium.common.exceptions import WebDriverException

from config import (
    ARTICLE_FETCH_COOLDOWN,
    ARTICLE_LOAD_WAIT_TIME,
    ECONOMIST_URL,
)
from models import Article, Edition
from utils import (
    EditionParseError,
    extract_date_from_cover_url, extract_date_from_text,
    has_extractable_content, save_debug_html,
)
from browser import BrowserManager, is_cloudflare_challenge
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

    def initialize(self) -> None:
        """Start Chrome, log in, and keep the browser for page fetches."""
        self.browser.setup()
        self.browser.login()
        print("Using headless Chrome for scraping")
    def _recover_session(self) -> bool:
        """Restart browser login after a tab crash or block."""
        print("  Recovering authenticated Chrome session...")
        try:
            self.browser.setup()
            self.browser.login()
            return True
        except Exception as exc:
            print(f"  Session recovery failed: {exc}")
            return False

    def _html_is_blocked(self, html: str) -> bool:
        """Return True when HTML is a Cloudflare wall or login paywall."""
        title = ""
        if self.browser.driver:
            try:
                title = self.browser.driver.title or ""
            except WebDriverException:
                title = ""
        if is_cloudflare_challenge(title, html):
            return True
        snippet = (html or "")[:8000].lower()
        paywall_markers = (
            "already have an account?",
            "continue with a free trial",
            "create account to unlock",
            "get full access to our independent journalism",
        )
        return any(marker in snippet for marker in paywall_markers)

    def _fetch_page(self, url: str, wait_time: int = 0) -> str:
        """Fetch a page with the authenticated Chrome session."""
        if not self.browser.driver:
            if not self._recover_session():
                raise RuntimeError("Browser not initialized")

        recovered = False
        last_error: Optional[Exception] = None
        settle = wait_time if wait_time else ARTICLE_LOAD_WAIT_TIME

        for _attempt in range(3):
            try:
                html = self.browser.navigate(url, wait_time=settle)
            except (WebDriverException, RuntimeError) as exc:
                last_error = exc
                if not recovered and self._recover_session():
                    recovered = True
                    continue
                raise

            if self._html_is_blocked(html):
                if not recovered and self._recover_session():
                    recovered = True
                    continue
                raise RuntimeError(
                    f"Cloudflare or login wall still present for {url}"
                )
            return html

        if last_error:
            raise last_error
        raise RuntimeError(f"Failed to fetch {url}")

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

        try:
            article_links = self.extractor.extract_edition_articles(html)
        except EditionParseError as exc:
            print(f"\nWeekly edition parse failed: {exc.reason}")
            if exc.details:
                print(f"  {exc.details}")
            raise

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

    def scrape_articles(
        self,
        limit: Optional[int] = None,
        until_section: Optional[str] = None,
    ) -> List[Article]:
        """Scrape multiple articles with optional limit.

        Args:
            limit: Maximum number of articles to scrape.
            until_section: If set, scrape through this section (inclusive)
                in edition order, then stop.

        Returns:
            List of successfully scraped articles.
        """
        articles = self.edition.articles

        if until_section:
            articles = self._articles_until_section(articles, until_section)
            print(f"\n📎 Scraping through section '{until_section}' "
                  f"({len(articles)} articles)")

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

    def _articles_until_section(
        self, articles: List[Article], until_section: str
    ) -> List[Article]:
        """Return articles from start through until_section inclusive."""
        target = until_section.strip().lower()
        section_order: List[str] = []
        for article in articles:
            section = article.section or 'Unknown'
            if section not in section_order:
                section_order.append(section)

        matched = next(
            (s for s in section_order if s.lower() == target),
            None,
        )
        if matched is None:
            available = ', '.join(section_order)
            raise ValueError(
                f"Section '{until_section}' not found. Available: {available}"
            )

        cutoff_index = section_order.index(matched)
        allowed = set(section_order[:cutoff_index + 1])
        return [a for a in articles if (a.section or 'Unknown') in allowed]

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

    def _print_section_counts(self) -> None:
        """Print article counts by section in edition order."""
        section_order: List[str] = []
        counts: dict[str, int] = {}

        for article in self.edition.articles:
            section = article.section or 'Unknown'
            if section not in counts:
                section_order.append(section)
                counts[section] = 0
            counts[section] += 1

        print("\nArticles by section:")
        for section in section_order:
            print(f"  {section}: {counts[section]}")
