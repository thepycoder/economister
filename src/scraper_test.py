"""Tests for the scraper module."""

import unittest
from unittest.mock import Mock, patch, MagicMock
from scraper import EconomistScraper
from models import Article, Edition
from test_fixtures import (
    MOCK_ARTICLE_JOBS_HTML,
    MOCK_WEEKLY_EDITION_HTML,
    MOCK_WEEKLY_EDITION_WTW_HTML,
)


class TestEconomistScraper(unittest.TestCase):
    """Test EconomistScraper class."""

    def setUp(self):
        """Set up test fixtures."""
        self.scraper = EconomistScraper(debug=False)

    @patch('scraper.BrowserManager')
    def test_initialize(self, mock_browser_class):
        """Test scraper initialization."""
        mock_browser = Mock()
        mock_browser_class.return_value = mock_browser

        scraper = EconomistScraper()
        scraper.initialize()

        mock_browser.setup.assert_called_once()
        mock_browser.login.assert_called_once()

    @patch('scraper.save_debug_html')
    @patch('scraper.BrowserManager')
    def test_scrape_weekly_edition(self, mock_browser_class, mock_save_debug):
        """Test scraping weekly edition page."""
        mock_browser = Mock()
        mock_browser.navigate.return_value = MOCK_WEEKLY_EDITION_HTML
        mock_browser_class.return_value = mock_browser

        scraper = EconomistScraper(debug=True)
        edition = scraper.scrape_weekly_edition()

        # Check navigation
        mock_browser.navigate.assert_called_once_with(
            "https://www.economist.com/weeklyedition"
        )

        # Check debug HTML saved
        mock_save_debug.assert_called_once()

        # Check edition data
        self.assertIsInstance(edition, Edition)
        self.assertIsNotNone(edition.date)
        self.assertIsNotNone(edition.cover_url)
        self.assertGreater(len(edition.articles), 0)

        # Check articles have sections
        for article in edition.articles:
            self.assertIsNotNone(article.section)
            self.assertIsNotNone(article.title)
            self.assertIsNotNone(article.url)

    @patch('scraper.save_debug_html')
    @patch('scraper.BrowserManager')
    def test_scrape_article_success(self, mock_browser_class, mock_save_debug):
        """Test successful article scraping."""
        mock_browser = Mock()
        mock_browser.navigate.return_value = MOCK_ARTICLE_JOBS_HTML
        mock_browser_class.return_value = mock_browser

        scraper = EconomistScraper(debug=True)
        article = Article(
            title="Test Article",
            url="https://example.com/article"
        )

        result = scraper.scrape_article(article)

        self.assertTrue(result)
        self.assertGreater(article.paragraph_count, 0)
        mock_browser.navigate.assert_called_once_with(
            "https://example.com/article",
            wait_time=3
        )
        mock_save_debug.assert_called_once()

    @patch('scraper.BrowserManager')
    def test_scrape_article_no_url(self, mock_browser_class):
        """Test scraping article without URL."""
        scraper = EconomistScraper()
        article = Article(title="No URL Article")

        result = scraper.scrape_article(article)

        self.assertFalse(result)

    @patch('scraper.BrowserManager')
    def test_scrape_article_too_short(self, mock_browser_class):
        """Test scraping article with insufficient content."""
        mock_browser = Mock()
        mock_browser.navigate.return_value = """
        <html>
            <h1>Short Article</h1>
            <div data-component="article-body">
                <p class="e1y9q0ei">Too short.</p>
            </div>
        </html>
        """
        mock_browser_class.return_value = mock_browser

        scraper = EconomistScraper()
        article = Article(url="https://example.com/short")

        result = scraper.scrape_article(article)

        self.assertFalse(result)

    @patch('scraper.BrowserManager')
    def test_scrape_article_error(self, mock_browser_class):
        """Test article scraping with error."""
        mock_browser = Mock()
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
        for i in range(10):
            scraper.edition.articles.append(
                Article(
                    title=f"Article {i}",
                    url=f"https://example.com/article{i}",
                    section="Test"
                )
            )

        # Scrape with limit
        results = scraper.scrape_articles(limit=5)

        self.assertEqual(len(results), 5)
        self.assertEqual(mock_scrape_article.call_count, 5)

    @patch('scraper.EconomistScraper.scrape_article')
    def test_scrape_articles_partial_success(self, mock_scrape_article):
        """Test scraping with some failures."""
        # Alternate between success and failure
        mock_scrape_article.side_effect = [True, False, True, False, True]

        scraper = EconomistScraper()

        for i in range(5):
            scraper.edition.articles.append(
                Article(
                    title=f"Article {i}",
                    url=f"https://example.com/article{i}"
                )
            )

        results = scraper.scrape_articles()

        self.assertEqual(len(results), 3)  # Only successful ones

    @patch('scraper.BrowserManager')
    def test_cleanup(self, mock_browser_class):
        """Test cleanup method."""
        mock_browser = Mock()
        mock_browser_class.return_value = mock_browser

        scraper = EconomistScraper()
        scraper.cleanup()

        mock_browser.quit.assert_called_once()

    def test_extract_edition_date_from_cover(self):
        """Test edition date extraction from cover URL."""
        self.scraper.extractor.extract_cover_url = Mock(
            return_value="https://example.com/20241215_DE_US.jpg"
        )

        html = "<html>Test</html>"
        self.scraper._extract_edition_date(html)

        self.assertEqual(self.scraper.edition.date, "2024-12-15")

    def test_extract_edition_date_from_text(self):
        """Test edition date extraction from page text."""
        self.scraper.extractor.extract_cover_url = Mock(return_value=None)

        html = "<html>December 15 2024 Edition</html>"
        self.scraper._extract_edition_date(html)

        self.assertEqual(self.scraper.edition.date, "2024-12-15")

    @patch('scraper.print')
    def test_print_section_counts(self, mock_print):
        """Test section count printing."""
        # Add articles in different sections
        self.scraper.edition.articles.extend([
            Article(section="Leaders"),
            Article(section="Leaders"),
            Article(section="Business"),
            Article(section="Other"),
        ])

        self.scraper._print_section_counts()

        # Check print was called for each section
        print_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any("Leaders: 2" in str(call) for call in print_calls))
        self.assertTrue(any("Business: 1" in str(call) for call in print_calls))
        self.assertTrue(any("Other: 1" in str(call) for call in print_calls))

    def test_sort_edition_articles_wtw_order(self):
        """WTW articles sort Politics before Business before Cartoon."""
        links = [
            {
                'title': 'Cartoon',
                'url': 'https://www.economist.com/the-world-this-week/2026/07/09/cartoon-x',
                'section': 'The world this week',
            },
            {
                'title': 'Business',
                'url': 'https://www.economist.com/the-world-this-week/2026/07/09/business',
                'section': 'The world this week',
            },
            {
                'title': 'Politics',
                'url': 'https://www.economist.com/the-world-this-week/2026/07/09/politics',
                'section': 'The world this week',
            },
        ]
        sorted_links = self.scraper._sort_edition_articles(links)
        titles = [link['title'] for link in sorted_links]
        self.assertEqual(titles, ['Politics', 'Business', 'Cartoon'])

    @patch('scraper.save_debug_html')
    @patch('scraper.BrowserManager')
    def test_scrape_weekly_edition_includes_wtw(
        self, mock_browser_class, mock_save_debug
    ):
        """Weekly edition scrape discovers short-label WTW links."""
        mock_browser = Mock()
        mock_browser.navigate.return_value = MOCK_WEEKLY_EDITION_WTW_HTML
        mock_browser_class.return_value = mock_browser

        scraper = EconomistScraper()
        edition = scraper.scrape_weekly_edition()

        wtw = [a for a in edition.articles if a.section == 'The world this week']
        self.assertEqual(len(wtw), 3)
        self.assertEqual(wtw[0].title, 'Politics')
        self.assertEqual(wtw[1].title, 'Business')


if __name__ == '__main__':
    unittest.main()
