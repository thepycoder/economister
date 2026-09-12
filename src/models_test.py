"""Tests for the models module."""

import unittest
from models import Article, ContentBlock, Edition, ImageBlock


class TestImageBlock(unittest.TestCase):
    """Test ImageBlock data class."""

    def test_image_block_creation(self):
        """Test creating an ImageBlock."""
        img = ImageBlock(
            src="https://example.com/image.jpg",
            caption="Test caption",
            credit="Photo: Test Credit",
            is_hero=True
        )
        self.assertEqual(img.src, "https://example.com/image.jpg")
        self.assertEqual(img.caption, "Test caption")
        self.assertEqual(img.credit, "Photo: Test Credit")
        self.assertTrue(img.is_hero)

    def test_image_block_defaults(self):
        """Test ImageBlock with default values."""
        img = ImageBlock(src="https://example.com/image.jpg")
        self.assertIsNone(img.caption)
        self.assertIsNone(img.credit)
        self.assertFalse(img.is_hero)


class TestContentBlock(unittest.TestCase):
    """Test ContentBlock data class."""

    def test_paragraph_block(self):
        """Test creating a paragraph content block."""
        block = ContentBlock(
            type='paragraph',
            content='Lorem ipsum dolor sit amet'
        )
        self.assertEqual(block.type, 'paragraph')
        self.assertEqual(block.content, 'Lorem ipsum dolor sit amet')
        self.assertIsNone(block.image)

    def test_image_content_block(self):
        """Test creating an image content block."""
        img = ImageBlock(src="https://example.com/image.jpg")
        block = ContentBlock(type='image', image=img)
        self.assertEqual(block.type, 'image')
        self.assertIsNone(block.content)
        self.assertEqual(block.image.src, "https://example.com/image.jpg")


class TestArticle(unittest.TestCase):
    """Test Article data class."""

    def test_article_creation(self):
        """Test creating an Article."""
        article = Article(
            title="Test Article",
            subtitle="Test Subtitle",
            url="https://example.com/article",
            section="Technology"
        )
        self.assertEqual(article.title, "Test Article")
        self.assertEqual(article.subtitle, "Test Subtitle")
        self.assertEqual(article.url, "https://example.com/article")
        self.assertEqual(article.section, "Technology")
        self.assertEqual(len(article.content_blocks), 0)

    def test_add_paragraph(self):
        """Test adding paragraphs to an article."""
        article = Article()
        article.add_paragraph("First paragraph")
        article.add_paragraph("Second paragraph")

        self.assertEqual(article.paragraph_count, 2)
        self.assertEqual(article.content_blocks[0].type, 'paragraph')
        self.assertEqual(article.content_blocks[0].content, "First paragraph")

    def test_add_image(self):
        """Test adding images to an article."""
        article = Article()
        article.add_image(
            src="https://example.com/image.jpg",
            caption="Test caption",
            credit="Test credit",
            is_hero=True
        )

        self.assertEqual(article.image_count, 1)
        self.assertEqual(article.content_blocks[0].type, 'image')
        self.assertEqual(article.content_blocks[0].image.caption, "Test caption")

    def test_mixed_content(self):
        """Test article with mixed paragraph and image content."""
        article = Article()
        article.add_paragraph("Opening paragraph")
        article.add_image(src="https://example.com/img1.jpg")
        article.add_paragraph("Middle paragraph")
        article.add_image(src="https://example.com/img2.jpg")
        article.add_paragraph("Closing paragraph")

        self.assertEqual(article.paragraph_count, 3)
        self.assertEqual(article.image_count, 2)
        self.assertEqual(len(article.content_blocks), 5)


class TestEdition(unittest.TestCase):
    """Test Edition data class."""

    def test_edition_creation(self):
        """Test creating an Edition."""
        edition = Edition(
            date="2024-12-15",
            title="TechWeekly - December 15, 2024",
            identifier="techweekly-20241215",
            cover_url="https://example.com/cover.jpg"
        )
        self.assertEqual(edition.date, "2024-12-15")
        self.assertEqual(edition.title, "TechWeekly - December 15, 2024")
        self.assertEqual(edition.identifier, "techweekly-20241215")
        self.assertEqual(edition.cover_url, "https://example.com/cover.jpg")
        self.assertEqual(len(edition.articles), 0)
        self.assertEqual(edition.scrape_summary.indexed_articles, 0)
        self.assertEqual(edition.scrape_summary.failed_articles, [])

    def test_articles_by_section(self):
        """Test grouping articles by section."""
        edition = Edition()

        # Add articles in different sections
        article1 = Article(title="Article 1", section="Technology")
        article2 = Article(title="Article 2", section="Business")
        article3 = Article(title="Article 3", section="Technology")
        article4 = Article(title="Article 4", section="Science")

        edition.articles.extend([article1, article2, article3, article4])

        sections = edition.articles_by_section()

        self.assertEqual(len(sections), 3)
        self.assertEqual(len(sections["Technology"]), 2)
        self.assertEqual(len(sections["Business"]), 1)
        self.assertEqual(len(sections["Science"]), 1)
        self.assertEqual(sections["Technology"][0].title, "Article 1")
        self.assertEqual(sections["Technology"][1].title, "Article 3")


if __name__ == '__main__':
    unittest.main()
