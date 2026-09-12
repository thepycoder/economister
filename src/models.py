"""Data models for the Economist EPUB generator."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ImageBlock:
    """Represents an image in an article."""
    src: str
    caption: Optional[str] = None
    credit: Optional[str] = None
    is_hero: bool = False


@dataclass
class ContentBlock:
    """Represents a content block in an article."""
    type: str  # 'paragraph' or 'image'
    content: Optional[str] = None  # For paragraphs
    image: Optional[ImageBlock] = None  # For images


@dataclass
class Article:
    """Represents an article with its content."""
    title: Optional[str] = None
    subtitle: Optional[str] = None
    url: Optional[str] = None
    section: Optional[str] = None
    content_blocks: List[ContentBlock] = field(default_factory=list)

    def add_paragraph(self, content: str) -> None:
        """Add a paragraph block to the article."""
        self.content_blocks.append(
            ContentBlock(type='paragraph', content=content)
        )

    def add_image(self, src: str, caption: Optional[str] = None,
                  credit: Optional[str] = None, is_hero: bool = False) -> None:
        """Add an image block to the article."""
        self.content_blocks.append(
            ContentBlock(
                type='image',
                image=ImageBlock(
                    src=src,
                    caption=caption,
                    credit=credit,
                    is_hero=is_hero
                )
            )
        )

    @property
    def paragraph_count(self) -> int:
        """Count paragraphs in the article."""
        return sum(1 for block in self.content_blocks
                   if block.type == 'paragraph')

    @property
    def image_count(self) -> int:
        """Count images in the article."""
        return sum(1 for block in self.content_blocks
                   if block.type == 'image')


@dataclass
class ScrapeSummary:
    """Records the completeness and recovery state of a scrape."""
    indexed_articles: int = 0
    selected_articles: int = 0
    failed_articles: List[str] = field(default_factory=list)
    access_blocks: int = 0
    session_recoveries: int = 0


@dataclass
class Edition:
    """Represents a weekly edition of The Economist."""
    date: Optional[str] = None
    title: Optional[str] = None
    identifier: Optional[str] = None
    articles: List[Article] = field(default_factory=list)
    cover_url: Optional[str] = None
    scrape_summary: ScrapeSummary = field(default_factory=ScrapeSummary)

    def articles_by_section(self) -> Dict[str, List[Article]]:
        """Group articles by section."""
        sections = {}
        for article in self.articles:
            if article.section not in sections:
                sections[article.section] = []
            sections[article.section].append(article)
        return sections
