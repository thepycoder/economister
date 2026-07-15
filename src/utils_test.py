"""Tests for the utils module."""

import unittest
from datetime import datetime
from pathlib import Path
import tempfile
import shutil
from models import Article
from utils import (
    create_directories, sanitize_filename, save_debug_html,
    convert_symbols, parse_edition_date, extract_date_from_cover_url,
    extract_date_from_text, is_valid_article_url,
    has_extractable_content,
    is_cartoon_url,
)


class TestDirectoryCreation(unittest.TestCase):
    """Test directory creation functions."""

    def setUp(self):
        """Set up test directory."""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = Path.cwd()
        import os
        os.chdir(self.test_dir)

    def tearDown(self):
        """Clean up test directory."""
        import os
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_create_directories(self):
        """Test creating necessary directories."""
        create_directories(debug=False)
        self.assertTrue(Path('ebooks').exists())
        self.assertTrue(Path('logs').exists())
        self.assertFalse(Path('debug').exists())

        create_directories(debug=True)
        self.assertTrue(Path('debug').exists())


class TestFilenameUtils(unittest.TestCase):
    """Test filename utility functions."""

    def test_sanitize_filename(self):
        """Test filename sanitization."""
        # Normal text
        self.assertEqual(sanitize_filename("Hello World"), "Hello World")

        # Special characters
        self.assertEqual(sanitize_filename("Hello/World\\Test"), "HelloWorldTest")

        # Path traversal attempts
        self.assertEqual(sanitize_filename("../../../etc/passwd"), "etcpasswd")

        # Long filename
        long_name = "a" * 100
        result = sanitize_filename(long_name, max_length=50)
        self.assertEqual(len(result), 50)

        # Empty string
        self.assertEqual(sanitize_filename(""), "untitled")

        # Only special characters
        self.assertEqual(sanitize_filename("@#$%^&*()"), "untitled")

    def test_save_debug_html(self):
        """Test saving debug HTML files."""
        test_dir = tempfile.mkdtemp()
        Path(test_dir, 'debug').mkdir()

        original_cwd = Path.cwd()
        import os
        os.chdir(test_dir)

        try:
            # Debug disabled - should not create file
            save_debug_html("test", "<html>test</html>", debug=False)
            self.assertEqual(len(list(Path('debug').glob('*.html'))), 0)

            # Debug enabled - should create file
            save_debug_html("test_article", "<html>test</html>", debug=True)
            files = list(Path('debug').glob('*.html'))
            self.assertEqual(len(files), 1)

            # Check file content
            with open(files[0], 'r') as f:
                content = f.read()
            self.assertEqual(content, "<html>test</html>")
        finally:
            os.chdir(original_cwd)
            shutil.rmtree(test_dir)


class TestTextProcessing(unittest.TestCase):
    """Test text processing functions."""

    def test_convert_symbols(self):
        """Test symbol conversion."""
        # Trademark
        self.assertEqual(convert_symbols("ProductTM"), "Product™")
        self.assertEqual(convert_symbols("Product(TM)"), "Product™")

        # Registered
        self.assertEqual(convert_symbols("Brand(R)"), "Brand®")

        # Copyright
        self.assertEqual(convert_symbols("Copyright (C) 2024"), "Copyright © 2024")
        self.assertEqual(convert_symbols("(C) 2024"), "© 2024")

        # Mixed
        text = "ProductTM is a Brand(R). Copyright (C) 2024"
        expected = "Product™ is a Brand®. Copyright © 2024"
        self.assertEqual(convert_symbols(text), expected)


class TestDateParsing(unittest.TestCase):
    """Test date parsing functions."""

    def test_parse_edition_date(self):
        """Test parsing edition date."""
        # Valid date
        title, id = parse_edition_date("2024-12-15")
        self.assertEqual(title, "The Economist - December 15, 2024")
        self.assertEqual(id, "economist-20241215")

        # None date - uses current date
        title, id = parse_edition_date(None)
        self.assertIn("The Economist", title)
        self.assertIn("economist-", id)

    def test_extract_date_from_cover_url(self):
        """Test extracting date from cover URL."""
        # Valid cover URL
        url = "https://example.com/content/20241215_DE_US.jpg"
        date = extract_date_from_cover_url(url)
        self.assertEqual(date, "2024-12-15")

        # Invalid URL
        url = "https://example.com/image.jpg"
        date = extract_date_from_cover_url(url)
        self.assertIsNone(date)

    def test_extract_date_from_text(self):
        """Test extracting date from HTML text."""
        # Various date formats
        html = "Published on December 15 2024"
        date = extract_date_from_text(html)
        self.assertEqual(date, "2024-12-15")

        html = "January 1 2024 edition"
        date = extract_date_from_text(html)
        self.assertEqual(date, "2024-01-01")

        html = "March 31 2024"
        date = extract_date_from_text(html)
        self.assertEqual(date, "2024-03-31")

        # No date
        html = "Lorem ipsum dolor sit amet"
        date = extract_date_from_text(html)
        self.assertIsNone(date)


class TestURLValidation(unittest.TestCase):
    """Test URL validation functions."""

    def test_is_valid_article_url(self):
        """Test article URL validation."""
        # Valid URLs
        self.assertTrue(is_valid_article_url(
            "/2024/12/15/test-article",
            "Test Article Title"
        ))

        # Invalid - wrong date format
        self.assertFalse(is_valid_article_url(
            "/2023/12/15/test",
            "Test"
        ))

        # Invalid - too short title
        self.assertFalse(is_valid_article_url(
            "/2024/12/15/test",
            "Test"
        ))

        # Invalid - skip patterns
        self.assertFalse(is_valid_article_url(
            "/2024/12/15/podcasts/test",
            "Test Podcast Episode"
        ))

        # Interactive path — regular articles (photo essays), not skipped
        self.assertTrue(is_valid_article_url(
            "/interactive/middle-east-and-africa/2026/07/08/is-donald-trump-serious",
            "Is Donald Trump serious in declaring the ceasefire with Iran over?"
        ))

        # WTW short TOC labels
        self.assertTrue(is_valid_article_url(
            "/the-world-this-week/2026/07/09/politics",
            "Politics"
        ))
        self.assertTrue(is_valid_article_url(
            "/the-world-this-week/2026/07/09/business",
            "Business"
        ))

    def test_cartoon_url_and_extractable_content(self):
        """Test cartoon URL detection and extractable content checks."""
        self.assertTrue(
            is_cartoon_url(
                "https://www.economist.com/the-world-this-week/"
                "2026/07/09/cartoon-the-real-threat"
            )
        )
        self.assertFalse(
            is_cartoon_url(
                "https://www.economist.com/the-world-this-week/"
                "2026/07/09/politics"
            )
        )
        article = Article(url="https://example.com/indicators")
        article.add_image(src="https://example.com/table.png")
        self.assertTrue(has_extractable_content(article))
        empty = Article(url="https://example.com/empty")
        self.assertFalse(has_extractable_content(empty))

        # Invalid - malicious URLs
        self.assertFalse(is_valid_article_url(
            "javascript:alert('xss')",
            "Malicious Link"
        ))

        # Invalid - None or empty
        self.assertFalse(is_valid_article_url(None, "Test"))
        self.assertFalse(is_valid_article_url("", "Test"))


if __name__ == '__main__':
    unittest.main()

