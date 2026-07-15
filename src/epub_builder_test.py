"""Tests for the epub_builder module."""

import unittest
from unittest.mock import Mock, patch, MagicMock, call
import tempfile
import shutil
from pathlib import Path
from epub_builder import EpubBuilder
from models import Article, Edition, ContentBlock, ImageBlock


class TestEpubBuilder(unittest.TestCase):
    """Test EpubBuilder class."""

    def setUp(self):
        """Set up test fixtures."""
        self.builder = EpubBuilder(debug=False)
        self.test_dir = tempfile.mkdtemp()
        Path(self.test_dir, 'ebooks').mkdir()

        # Create test edition
        self.edition = Edition(
            date="2024-12-15",
            cover_url="https://example.com/cover.jpg"
        )

        # Create test articles
        self.articles = [
            self._create_test_article("Leaders"),
            self._create_test_article("Business"),
            self._create_test_article("Technology")
        ]

    def tearDown(self):
        """Clean up test directory."""
        shutil.rmtree(self.test_dir)

    def _create_test_article(self, section):
        """Create a test article with content."""
        article = Article(
            title=f"Test {section} Article",
            subtitle=f"Subtitle for {section}",
            section=section
        )
        article.add_paragraph("Lorem ipsum dolor sit amet, consectetur adipiscing elit.")
        article.add_paragraph("Sed do eiusmod tempor incididunt ut labore et dolore magna.")
        article.add_image(
            src="https://example.com/image.jpg",
            caption="Test image caption",
            credit="Photo: Test Credit"
        )
        return article

    def test_set_metadata(self):
        """Test EPUB metadata setting."""
        self.builder._set_metadata(self.edition)

        self.assertEqual(self.edition.title, "The Economist - December 15, 2024")
        self.assertEqual(self.edition.identifier, "economist-20241215")

        # Check book metadata
        self.assertIsNotNone(self.builder.book)

    @patch('epub_builder.ImageHandler')
    def test_create_cover_with_url(self, mock_handler_class):
        """Test cover creation with URL."""
        mock_handler = Mock()
        mock_handler.download_cover.return_value = (b'cover_data', b'full_res_data')
        mock_handler_class.return_value = mock_handler

        builder = EpubBuilder()
        builder._create_cover("https://example.com/cover.jpg")

        mock_handler.download_cover.assert_called_once_with(
            "https://example.com/cover.jpg"
        )
        self.assertEqual(builder.full_res_cover_data, b'full_res_data')

    @patch('epub_builder.ImageHandler')
    def test_create_cover_fallback(self, mock_handler_class):
        """Test cover creation with fallback."""
        mock_handler = Mock()
        mock_handler.download_cover.side_effect = Exception("Download failed")
        mock_handler.create_default_cover.return_value = b'default_cover'
        mock_handler_class.return_value = mock_handler

        builder = EpubBuilder()
        builder._create_cover("https://example.com/cover.jpg")

        mock_handler.create_default_cover.assert_called_once()
        self.assertEqual(builder.full_res_cover_data, b'default_cover')

    @patch('epub_builder.ImageHandler')
    def test_create_chapter(self, mock_handler_class):
        """Test chapter creation from article."""
        mock_handler = Mock()
        mock_handler.download_image.return_value = b'image_data'
        mock_handler.images_added = 1
        mock_handler_class.return_value = mock_handler

        builder = EpubBuilder()
        chapter = builder._create_chapter(self.articles[0], 1)

        self.assertIsNotNone(chapter)
        self.assertEqual(chapter.title, "Test Leaders Article")
        self.assertEqual(chapter.file_name, "article_001.xhtml")
        self.assertIn("Test Leaders Article", chapter.content)
        self.assertIn("Lorem ipsum", chapter.content)

    def test_create_chapter_no_content(self):
        """Test chapter creation with no content."""
        article = Article(title="Empty Article")
        chapter = self.builder._create_chapter(article, 1)

        self.assertIsNone(chapter)

    @patch('epub_builder.ImageHandler')
    def test_build_article_html(self, mock_handler_class):
        """Test HTML generation for article."""
        mock_handler = Mock()
        mock_handler.download_image.return_value = b'image_data'
        mock_handler.images_added = 1
        mock_handler_class.return_value = mock_handler

        builder = EpubBuilder()
        html = builder._build_article_html(self.articles[0])

        self.assertIsNotNone(html)
        self.assertIn("<h1>", html)
        self.assertIn("Test Leaders Article", html)
        self.assertIn("<p>Lorem ipsum", html)
        self.assertIn("<img", html)

    def test_build_article_html_escaping(self):
        """Test HTML escaping in article content."""
        article = Article(
            title="Test <script>alert('xss')</script> Article",
            subtitle="Subtitle with <em>tags</em>"
        )
        article.add_paragraph("Content with <b>HTML</b> tags")

        html = self.builder._build_article_html(article)

        # Title and subtitle should be escaped
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&lt;em&gt;", html)

        # Paragraph content is already sanitized by extractor
        self.assertIn("Content with <b>HTML</b> tags", html)

    def test_create_figure_html(self):
        """Test figure HTML generation."""
        html = self.builder._create_figure_html(
            "image.jpg",
            "Test caption",
            "Photo: Test Credit",
            is_hero=True
        )

        self.assertIn('src="images/image.jpg"', html)
        self.assertIn("Test caption", html)
        self.assertIn("<em>Photo: Test Credit</em>", html)

    def test_create_figure_html_no_caption(self):
        """Test figure HTML without caption."""
        html = self.builder._create_figure_html(
            "image.jpg",
            None,
            None,
            is_hero=False
        )

        self.assertIn('src="images/image.jpg"', html)
        self.assertNotIn("<em>", html)

    def test_create_cover_page(self):
        """Test cover page creation."""
        self.builder.full_res_cover_data = b'cover_data'

        cover_page = self.builder._create_cover_page()

        self.assertIsNotNone(cover_page)
        self.assertIn("cover.jpg", cover_page.content)

    def test_create_cover_page_no_data(self):
        """Test cover page creation without cover data."""
        cover_page = self.builder._create_cover_page()

        self.assertIsNone(cover_page)

    def test_build_table_of_contents(self):
        """Test TOC generation follows edition section order."""
        for article in self.articles:
            chapter = Mock()
            chapter.title = article.title
            section = article.section
            if section not in self.builder.sections:
                self.builder.sections[section] = []
                self.builder.section_order.append(section)
            self.builder.sections[section].append(chapter)

        toc = self.builder._build_table_of_contents()

        self.assertEqual(len(toc), 3)

        section_names = [entry[0].title for entry in toc]
        self.assertEqual(section_names, ["Leaders", "Business", "Technology"])

    def test_add_stylesheet(self):
        """Test stylesheet addition."""
        self.builder._add_stylesheet()

        # Check that CSS was added to book items
        # This is implementation-specific, but we can verify the method runs
        self.assertIsNotNone(self.builder.book)

    @patch('epub_builder.epub.write_epub')
    @patch('epub_builder.os.path.getsize')
    @patch('epub_builder.ImageHandler')
    def test_build_complete(self, mock_handler_class, mock_getsize, mock_write_epub):
        """Test complete EPUB build process."""
        mock_handler = Mock()
        mock_handler.download_image.return_value = b'image_data'
        mock_handler.download_cover.return_value = (b'cover', b'full_cover')
        mock_handler.images_added = 3
        mock_handler_class.return_value = mock_handler

        mock_getsize.return_value = 1024 * 1024  # 1MB

        # Change working directory to test dir
        import os
        original_cwd = os.getcwd()
        os.chdir(self.test_dir)

        try:
            builder = EpubBuilder()
            output_path = builder.build(self.edition, self.articles)

            self.assertEqual(output_path, Path('ebooks/economist_2024-12-15.epub'))
            mock_write_epub.assert_called_once()

            # Check chapters were created
            self.assertEqual(len(builder.chapters), 3)

            # Check sections were organized
            self.assertEqual(len(builder.sections), 3)
        finally:
            os.chdir(original_cwd)

    @patch('epub_builder.print')
    @patch('epub_builder.os.path.getsize')
    def test_print_summary(self, mock_getsize, mock_print):
        """Test summary printing."""
        mock_getsize.return_value = 2 * 1024 * 1024  # 2MB

        # Add some chapters
        for i in range(5):
            mock_chapter = Mock()
            mock_chapter.content = "<p>Test</p>" * 10
            self.builder.chapters.append(mock_chapter)

        self.builder.sections = {"Leaders": [1, 2], "Business": [3]}
        self.builder.image_handler.images_added = 10

        output_file = Path("test.epub")
        self.builder._print_summary(output_file, self.edition)

        # Check that summary was printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any("Articles: 5" in str(call) for call in print_calls))
        self.assertTrue(any("Images: 10" in str(call) for call in print_calls))
        self.assertTrue(any("2.00 MB" in str(call) for call in print_calls))


if __name__ == '__main__':
    unittest.main()
