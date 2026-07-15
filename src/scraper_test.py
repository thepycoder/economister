"""Tests for the scraper module."""

import unittest
from unittest.mock import Mock, patch, MagicMock, ANY
from scraper import EconomistScraper
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

    def _mock_response(self, html: str) -> Mock:
        response = Mock()
        response.text = html
        response.raise_for_status = Mock()
        return response

    @patch('scraper.BrowserManager')
    def test_initialize(self, mock_browser_class):
        """Test scraper initialization."""
        mock_browser = Mock()
        mock_session = Mock()
        mock_browser.export_requests_session.return_value = mock_session
        mock_browser_class.return_value = mock_browser

        scraper = EconomistScraper()
        scraper.initialize()

        mock_browser.setup.assert_called_once()
        mock_browser.login.assert_called_once()
        mock_browser.export_requests_session.assert_called_once()
        mock_browser.quit.assert_called_once()
        self.assertEqual(scraper.session, mock_session)

    @patch('scraper.save_debug_html')
    @patch('scraper.BrowserManager')
    def test_scrape_weekly_edition(self, mock_browser_class, mock_save_debug):
        """Test scraping weekly edition page."""
        mock_session = Mock()
        mock_session.get.return_value = self._mock_response(
            MOCK_WEEKLY_EDITION_HTML
        )
        mock_browser = Mock()
        mock_browser.export_requests_session.return_value = mock_session
        mock_browser_class.return_value = mock_browser

        scraper = EconomistScraper(debug=True)
        scraper.session = mock_session
        edition = scraper.scrape_weekly_edition()

        mock_session.get.assert_called_once()
        self.assertEqual(
            mock_session.get.call_args[0][0],
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
        mock_session = Mock()
        mock_session.get.return_value = self._mock_response(
            MOCK_ARTICLE_JOBS_HTML
        )
        mock_browser_class.return_value = Mock()

        scraper = EconomistScraper(debug=True)
        scraper.session = mock_session
        article = Article(
            title="Test Article",
            url="https://example.com/article"
        )

        result = scraper.scrape_article(article)

        self.assertTrue(result)
        self.assertGreater(article.paragraph_count, 0)
        mock_session.get.assert_called_once_with(
            "https://example.com/article",
            timeout=30,
            headers={'User-Agent': ANY},
        )
        mock_save_debug.assert_called_once()

    @patch('scraper.save_debug_html')
    @patch('scraper.BrowserManager')
    def test_scrape_cartoon_with_single_paragraph(
        self, mock_browser_class, mock_save_debug
    ):
        """Test cartoon articles are kept when they include the image."""
        mock_session = Mock()
        mock_session.get.return_value = self._mock_response(MOCK_CARTOON_HTML)
        mock_browser_class.return_value = Mock()

        scraper = EconomistScraper(debug=True)
        scraper.session = mock_session
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
        mock_session = Mock()
        mock_session.get.return_value = self._mock_response(
            MOCK_INDICATORS_HTML
        )
        mock_browser_class.return_value = Mock()

        scraper = EconomistScraper(debug=True)
        scraper.session = mock_session
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
        mock_session = Mock()
        mock_session.get.return_value = self._mock_response("""
        <html>
            <h1>Empty Article</h1>
            <div data-component="article-body"></div>
        </html>
        """)
        mock_browser_class.return_value = Mock()

        scraper = EconomistScraper()
        scraper.session = mock_session
        article = Article(url="https://example.com/short")

        result = scraper.scrape_article(article)

        self.assertFalse(result)

    @patch('scraper.BrowserManager')
    def test_scrape_article_error(self, mock_browser_class):
        """Test article scraping with error."""
        mock_session = Mock()
        mock_session.get.side_effect = Exception("Network error")
        mock_browser = Mock()
        mock_browser.export_requests_session.return_value = mock_session
        mock_browser_class.return_value = mock_browser

        scraper = EconomistScraper()
        scraper.session = mock_session
        article = Article(url="https://example.com/error")

        with patch.object(scraper, '_recover_session', return_value=False):
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

        result = scraper.scrape_articles(limit=3)

        self.assertEqual(len(result), 3)
        self.assertEqual(mock_scrape_article.call_count, 3)

    @patch('scraper.EconomistScraper.scrape_article')
    def test_scrape_articles_no_limit(self, mock_scrape_article):
        """Test scraping all articles without limit."""
        mock_scrape_article.return_value = True

        scraper = EconomistScraper()

        for i in range(3):
            scraper.edition.articles.append(
                Article(title=f"Article {i}", url=f"https://example.com/{i}")
            )

        result = scraper.scrape_articles()

        self.assertEqual(len(result), 3)
        self.assertEqual(mock_scrape_article.call_count, 3)

    @patch('scraper.BrowserManager')
    def test_cleanup(self, mock_browser_class):
        """Test scraper cleanup."""
        mock_browser = Mock()
        mock_browser_class.return_value = mock_browser

        scraper = EconomistScraper()
        scraper.cleanup()

        mock_browser.quit.assert_called_once()

    @patch('scraper.save_debug_html')
    @patch('scraper.BrowserManager')
    def test_wtw_articles_included(
        self, mock_browser_class, mock_save_debug
    ):
        """Test WTW articles are extracted and sorted."""
        mock_session = Mock()
        mock_session.get.return_value = self._mock_response(
            MOCK_WEEKLY_EDITION_WTW_HTML
        )
        mock_browser_class.return_value = Mock()

        scraper = EconomistScraper(debug=True)
        scraper.session = mock_session
        edition = scraper.scrape_weekly_edition()

        wtw_articles = [
            a for a in edition.articles
            if a.section == 'The world this week'
        ]
        self.assertEqual(len(wtw_articles), 3)

        urls = [a.url for a in wtw_articles]
        self.assertTrue(any('/politics' in u for u in urls))
        self.assertTrue(any('/business' in u for u in urls))
        self.assertTrue(any('/cartoon' in u for u in urls))


if __name__ == "__main__":
    unittest.main()
