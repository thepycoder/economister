"""Tests for the scraper module."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from selenium.common.exceptions import WebDriverException
from scraper import AccessBlockedError, EconomistScraper
from models import Article, Edition
from test_fixtures import (
    MOCK_ARTICLE_JOBS_HTML,
    MOCK_CARTOON_HTML,
    MOCK_INDICATORS_HTML,
    MOCK_WEEKLY_EDITION_HTML,
    MOCK_WEEKLY_EDITION_WTW_HTML,
)


class TestEconomistScraper(unittest.TestCase):
    """Test EconomistScraper class."""

    def setUp(self):
        """Set up test fixtures."""
        self.scraper = EconomistScraper(debug=False)

    def _mock_response(
        self,
        html: str,
        url: str = "https://www.economist.com/test",
    ) -> Mock:
        response = Mock()
        response.text = html
        response.url = url
        response.status_code = 200
        response.raise_for_status = Mock()
        return response

    @patch('scraper.BrowserManager')
    def test_initialize(self, mock_browser_class):
        """Test scraper initialization."""
        mock_browser = Mock()
        mock_browser_class.return_value = mock_browser

        scraper = EconomistScraper()
        scraper.initialize()

        mock_browser.setup.assert_called_once()
        mock_browser.login.assert_called_once()
        mock_browser.quit.assert_not_called()

    def _mock_browser(self, html: str) -> Mock:
        mock_browser = Mock()
        mock_browser.navigate.return_value = html
        mock_browser.driver = Mock()
        mock_browser.driver.title = "The Economist"
        return mock_browser

    @patch('scraper.save_debug_html')
    @patch('scraper.BrowserManager')
    def test_scrape_weekly_edition(self, mock_browser_class, mock_save_debug):
        """Test scraping weekly edition page."""
        mock_browser = self._mock_browser(MOCK_WEEKLY_EDITION_HTML)
        mock_browser_class.return_value = mock_browser

        scraper = EconomistScraper(debug=True)
        edition = scraper.scrape_weekly_edition()

        mock_browser.navigate.assert_called_once()
        self.assertEqual(
            mock_browser.navigate.call_args[0][0],
            "https://www.economist.com/weeklyedition",
        )

        mock_save_debug.assert_called_once()

        self.assertIsInstance(edition, Edition)
        self.assertIsNotNone(edition.date)
        self.assertIsNotNone(edition.cover_url)
        self.assertGreater(len(edition.articles), 0)

        for article in edition.articles:
            self.assertIsNotNone(article.section)
            self.assertIsNotNone(article.title)
            self.assertIsNotNone(article.url)

    @patch('scraper.save_debug_html')
    @patch('scraper.BrowserManager')
    def test_scrape_article_success(self, mock_browser_class, mock_save_debug):
        """Test successful article scraping."""
        mock_browser = self._mock_browser(MOCK_ARTICLE_JOBS_HTML)
        mock_browser_class.return_value = mock_browser

        scraper = EconomistScraper(debug=True)
        article = Article(
            title="Test Article",
            url="https://example.com/article"
        )

        result = scraper.scrape_article(article)

        self.assertTrue(result)
        self.assertGreater(article.paragraph_count, 0)
        mock_browser.navigate.assert_called_once()
        self.assertEqual(
            mock_browser.navigate.call_args[0][0],
            "https://example.com/article",
        )
        mock_save_debug.assert_called_once()

    @patch('scraper.save_debug_html')
    @patch('scraper.BrowserManager')
    def test_scrape_cartoon_with_single_paragraph(
        self, mock_browser_class, mock_save_debug
    ):
        """Test cartoon articles are kept when they include the image."""
        mock_browser_class.return_value = self._mock_browser(MOCK_CARTOON_HTML)

        scraper = EconomistScraper(debug=True)
        article = Article(
            title="Cartoon: Test headline",
            url=(
                "https://www.economist.com/the-world-this-week/"
                "2026/07/09/cartoon-test-slug"
            ),
            section="The world this week",
        )

        result = scraper.scrape_article(article)

        self.assertTrue(result)
        self.assertGreaterEqual(article.image_count, 1)
        self.assertEqual(article.paragraph_count, 1)

    @patch('scraper.save_debug_html')
    @patch('scraper.BrowserManager')
    def test_scrape_image_only_article(
        self, mock_browser_class, mock_save_debug
    ):
        """Test image-only articles such as financial indicators are kept."""
        mock_browser_class.return_value = self._mock_browser(MOCK_INDICATORS_HTML)

        scraper = EconomistScraper(debug=True)
        article = Article(
            title="Economic data, commodities and markets",
            url=(
                "https://www.economist.com/economic-and-financial-indicators/"
                "2026/07/09/indicators"
            ),
            section="Economic & financial indicators",
        )

        result = scraper.scrape_article(article)

        self.assertTrue(result)
        self.assertEqual(article.paragraph_count, 0)
        self.assertGreaterEqual(article.image_count, 1)

    @patch('scraper.BrowserManager')
    def test_scrape_article_no_url(self, mock_browser_class):
        """Test scraping article without URL."""
        scraper = EconomistScraper()
        article = Article(title="No URL Article")

        result = scraper.scrape_article(article)

        self.assertFalse(result)

    @patch('scraper.BrowserManager')
    def test_scrape_article_too_short(self, mock_browser_class):
        """Test scraping article with no extractable content."""
        mock_browser_class.return_value = self._mock_browser("""
        <html>
            <h1>Empty Article</h1>
            <div data-component="article-body"></div>
        </html>
        """)

        scraper = EconomistScraper()
        article = Article(url="https://example.com/short")

        result = scraper.scrape_article(article)

        self.assertFalse(result)

    @patch('scraper.BrowserManager')
    def test_fetch_page_recovers_only_on_auth_failure(
        self, mock_browser_class
    ):
        """Test paywall HTML triggers one Chrome re-login; crashes recover too."""
        mock_browser = self._mock_browser("<html><h1>Article</h1></html>")
        mock_browser.navigate.side_effect = [
            "<html>Already have an account? Log in</html>",
            "<html><h1>Article</h1></html>",
        ]
        mock_browser_class.return_value = mock_browser

        scraper = EconomistScraper()

        with patch.object(
            scraper, '_recover_session', return_value=True
        ) as recover, patch('scraper.time.sleep') as sleep:
            html = scraper._fetch_page("https://www.economist.com/article")

        recover.assert_called_once()
        sleep.assert_called_once_with(300)
        self.assertIn("Article", html)

        recover.reset_mock()
        mock_browser.navigate.side_effect = WebDriverException("tab crashed")
        with patch.object(scraper, '_recover_session', return_value=False) as recover:
            with self.assertRaises(WebDriverException):
                scraper._fetch_page("https://www.economist.com/article")

        recover.assert_called_once()

    @patch('scraper.BrowserManager')
    def test_fetch_page_recovers_after_document_403(self, mock_browser_class):
        """A top-level 403 triggers backoff, re-login, and one retry."""
        mock_browser = self._mock_browser("<html><h1>Article</h1></html>")
        mock_browser.navigate.side_effect = [
            "<html>blocked</html>",
            "<html><h1>Article</h1></html>",
        ]
        mock_browser.collect_navigation_diagnostics.side_effect = [
            {
                'network_failures': [{
                    'kind': 'response',
                    'type': 'Document',
                    'status': 403,
                }],
            },
            {'network_failures': []},
        ]
        mock_browser_class.return_value = mock_browser
        scraper = EconomistScraper()

        with patch.object(
            scraper, '_recover_session', return_value=True
        ) as recover, patch('scraper.time.sleep') as sleep:
            html = scraper._fetch_page("https://www.economist.com/article")

        self.assertIn("Article", html)
        recover.assert_called_once()
        sleep.assert_called_once_with(300)

    @patch('scraper.BrowserManager')
    def test_fetch_page_aborts_after_repeated_document_403(
        self, mock_browser_class
    ):
        """A retry that is also blocked aborts the scrape."""
        mock_browser = self._mock_browser("<html>blocked</html>")
        diagnostic = {
            'network_failures': [{
                'kind': 'response',
                'type': 'Document',
                'status': 403,
            }],
        }
        mock_browser.collect_navigation_diagnostics.return_value = diagnostic
        mock_browser_class.return_value = mock_browser
        scraper = EconomistScraper()

        with patch.object(
            scraper, '_recover_session', return_value=True
        ) as recover, patch('scraper.time.sleep') as sleep:
            with self.assertRaises(AccessBlockedError):
                scraper._fetch_page("https://www.economist.com/article")

        self.assertEqual(mock_browser.navigate.call_count, 2)
        recover.assert_called_once()
        sleep.assert_called_once_with(300)

    @patch('scraper.BrowserManager')
    def test_scrape_article_propagates_access_block(self, mock_browser_class):
        """Persistent access blocks prevent a partial EPUB build."""
        mock_browser_class.return_value = self._mock_browser("")
        scraper = EconomistScraper()
        article = Article(url="https://www.economist.com/leaders/article")

        with patch.object(
            scraper,
            '_fetch_page',
            side_effect=AccessBlockedError("blocked"),
        ):
            with self.assertRaises(AccessBlockedError):
                scraper.scrape_article(article)

    @patch('scraper.BrowserManager')
    def test_scrape_article_error(self, mock_browser_class):
        """Test article scraping with error."""
        mock_browser = self._mock_browser("")
        mock_browser.navigate.side_effect = Exception("Network error")
        mock_browser_class.return_value = mock_browser

        scraper = EconomistScraper()
        article = Article(url="https://example.com/error")

        result = scraper.scrape_article(article)

        self.assertFalse(result)

    @patch('scraper.EconomistScraper.scrape_article')
    def test_scrape_articles_with_limit(self, mock_scrape_article):
        """Test scraping multiple articles with limit."""
        mock_scrape_article.return_value = True

        scraper = EconomistScraper()

        # Add test articles
        for i in range(5):
            scraper.edition.articles.append(
                Article(title=f"Article {i}", url=f"https://example.com/{i}")
            )

        with patch('scraper.time.sleep') as sleep:
            result = scraper.scrape_articles(limit=3)

        self.assertEqual(len(result), 3)
        self.assertEqual(mock_scrape_article.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        sleep.assert_called_with(8)

    @patch('scraper.EconomistScraper.scrape_article')
    def test_scrape_articles_no_limit(self, mock_scrape_article):
        """Test scraping all articles without limit."""
        mock_scrape_article.return_value = True

        scraper = EconomistScraper()

        for i in range(3):
            scraper.edition.articles.append(
                Article(title=f"Article {i}", url=f"https://example.com/{i}")
            )

        with patch('scraper.time.sleep') as sleep:
            result = scraper.scrape_articles()

        self.assertEqual(len(result), 3)
        self.assertEqual(mock_scrape_article.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        sleep.assert_called_with(8)

    @patch('scraper.BrowserManager')
    def test_cleanup(self, mock_browser_class):
        """Test scraper cleanup."""
        mock_browser = Mock()
        mock_browser_class.return_value = mock_browser

        scraper = EconomistScraper()
        scraper.cleanup()

        mock_browser.quit.assert_called_once()

    def test_diagnostics_persist_for_noninteractive_run(self):
        """Docker diagnostics are written to the mounted output directory."""
        scraper = EconomistScraper()

        with tempfile.TemporaryDirectory() as output_dir, patch(
            'scraper.NONINTERACTIVE', True
        ), patch('scraper.OUTPUT_DIR', output_dir), patch('builtins.print'):
            path = Path(output_dir) / 'economister_diagnostics.jsonl'
            path.write_text('stale\n')
            scraper._emit_diagnostic('session', run_id='test-run')
            scraper._emit_diagnostic('fetch', requested_url='https://example.com')
            records = [json.loads(line) for line in path.read_text().splitlines()]

        self.assertEqual([r['event'] for r in records], ['session', 'fetch'])
        self.assertEqual(records[0]['run_id'], 'test-run')

    @patch('scraper.save_debug_html')
    @patch('scraper.BrowserManager')
    def test_wtw_articles_included(
        self, mock_browser_class, mock_save_debug
    ):
        """Test WTW articles are extracted in DOM order."""
        mock_browser_class.return_value = self._mock_browser(
            MOCK_WEEKLY_EDITION_WTW_HTML
        )

        scraper = EconomistScraper(debug=True)
        edition = scraper.scrape_weekly_edition()

        self.assertEqual(len(edition.articles), 4)

        wtw_articles = [
            a for a in edition.articles
            if a.section == 'The world this week'
        ]
        self.assertEqual(len(wtw_articles), 4)

        slugs = [a.url.rstrip('/').split('/')[-1] for a in edition.articles]
        self.assertEqual(
            slugs,
            ['politics', 'business', 'cartoon-test-slug', 'sample-photo-essay'],
        )


if __name__ == "__main__":
    unittest.main()
