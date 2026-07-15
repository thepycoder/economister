"""EPUB file builder."""

import os
from pathlib import Path
from typing import List, Optional

from ebooklib import epub

from config import (
    COVER_PAGE_HTML, EPUB_STYLESHEET, MAX_IMAGES_PER_ARTICLE,
    SECTION_ORDER
)
from models import Article, Edition
from utils import parse_edition_date
from image_handler import ImageHandler


class EpubBuilder:
    """Builds EPUB files from scraped content."""

    def __init__(self, debug: bool = False):
        """Initialize EPUB builder.

        Args:
            debug: Enable debug output.
        """
        self.debug = debug
        self.book = epub.EpubBook()
        self.chapters = []
        self.sections = {}
        self.image_handler = ImageHandler(debug=debug)
        self.full_res_cover_data = None

    def build(self, edition: Edition,
              articles: List[Article]) -> Path:
        """Build EPUB from edition and articles.

        Args:
            edition: Edition metadata.
            articles: List of articles with content.

        Returns:
            Path to generated EPUB file.
        """
        # Set metadata
        self._set_metadata(edition)

        # Create cover
        self._create_cover(edition.cover_url)

        # Process articles (preserve edition order from scraper)
        for i, article in enumerate(articles, 1):
            chapter = self._create_chapter(article, i)
            if chapter:
                self.book.add_item(chapter)
                self.chapters.append(chapter)

                # Organize by section
                section = article.section or 'Other'
                if section not in self.sections:
                    self.sections[section] = []
                self.sections[section].append(chapter)

        # Create cover page
        cover_chapter = self._create_cover_page()

        # Build table of contents
        self.book.toc = tuple(self._build_table_of_contents())

        # Add stylesheet
        self._add_stylesheet()

        # Add navigation files
        self.book.add_item(epub.EpubNcx())
        self.book.add_item(epub.EpubNav())

        # Define spine
        if cover_chapter:
            self.book.spine = [cover_chapter, 'nav'] + self.chapters
        else:
            self.book.spine = ['nav'] + self.chapters

        # Write EPUB
        output_file = Path('ebooks') / f'economist_{edition.date}.epub'
        epub.write_epub(output_file, self.book, {})

        self._print_summary(output_file, edition)

        return output_file

    def _set_metadata(self, edition: Edition) -> None:
        """Set EPUB metadata from edition info."""
        title, edition_id = parse_edition_date(edition.date)

        self.book.set_identifier(edition_id)
        self.book.set_title(title)
        self.book.set_language('en')
        self.book.add_author('The Economist')
        self.book.add_metadata('DC', 'publisher', 'The Economist')
        self.book.add_metadata('DC', 'date', edition.date)

        edition.title = title
        edition.identifier = edition_id

    def _create_cover(self, cover_url: Optional[str]) -> None:
        """Create or fetch cover image for the EPUB."""
        print("Setting up cover...")

        cover_data = None
        full_res_cover_data = None

        if cover_url:
            try:
                cover_data, full_res_cover_data = (
                    self.image_handler.download_cover(cover_url)
                )
                print("  ✓ Cover image downloaded")
            except Exception as e:
                print(f"  ⚠ Could not fetch cover: {e}")

        # Create default cover if needed
        if not cover_data:
            cover_data = self.image_handler.create_default_cover()
            full_res_cover_data = cover_data
            print("  ✓ Default cover created")

        self.book.set_cover('cover.jpg', cover_data)
        self.full_res_cover_data = full_res_cover_data

    def _create_chapter(self, article: Article,
                        index: int) -> Optional[epub.EpubHtml]:
        """Create EPUB chapter from article.

        Args:
            article: Article with content.
            index: Chapter index number.

        Returns:
            EpubHtml chapter or None if failed.
        """
        if not article.content_blocks:
            return None

        # Build HTML content
        html_content = self._build_article_html(article)
        if not html_content:
            return None

        import html as html_module

        chapter = epub.EpubHtml(
            title=article.title or f"Article {index}",
            file_name=f'article_{index:03d}.xhtml',
            lang='en'
        )

        chapter.content = f'''<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>{html_module.escape(article.title or "")}</title>
    <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
{html_content}
</body>
</html>'''

        chapter.article_url = article.url
        return chapter

    def _build_article_html(self, article: Article) -> Optional[str]:
        """Build HTML content from article data.

        Args:
            article: Article with content blocks.

        Returns:
            HTML string of article content.
        """
        if not article.content_blocks:
            return None

        import html as html_module

        html_content = []

        if article.title:
            html_content.append(f'<h1>{html_module.escape(article.title)}</h1>')

        if article.subtitle:
            html_content.append(
                f'<p style="font-style: italic; color: #666;">'
                f'{html_module.escape(article.subtitle)}</p>'
            )

        images_added = 0

        for block in article.content_blocks:
            if block.type == 'paragraph' and block.content:
                html_content.append(f'<p>{block.content}</p>')

            elif (block.type == 'image' and block.image and
                  images_added < MAX_IMAGES_PER_ARTICLE):
                # Download and add image
                img_data = self.image_handler.download_image(block.image.src)
                if img_data:
                    # Add to EPUB
                    filename = f'image_{self.image_handler.images_added:03d}.jpg'
                    epub_img = epub.EpubItem(
                        uid=filename,
                        file_name=f'images/{filename}',
                        media_type='image/jpeg',
                        content=img_data
                    )
                    self.book.add_item(epub_img)

                    # Create figure HTML
                    figure_html = self._create_figure_html(
                        filename,
                        block.image.caption,
                        block.image.credit,
                        block.image.is_hero or images_added == 0
                    )
                    html_content.append(figure_html)
                    images_added += 1

        return '\n'.join(html_content) if html_content else None

    def _create_figure_html(
            self, img_file: str,
            caption: Optional[str],
            credit: Optional[str],
            is_hero: bool
    ) -> str:
        """Create HTML for figure element.

        Args:
            img_file: Image filename.
            caption: Image caption text.
            credit: Image credit text.
            is_hero: Whether this is a hero image.

        Returns:
            HTML string for the figure.
        """
        figure_html = (
            '<div style="width: 100%; margin: 1.5em 0; '
            'text-align: center;">\n'
            '    <div style="width: 90%; margin: 0 auto;">\n'
            f'        <img src="images/{img_file}" alt="Article image" '
            'style="width: 100%; height: auto; display: block;" />'
        )

        if caption or credit:
            figure_html += (
                '\n        <div style="margin-top: 0.5em; '
                'font-size: 0.9em; color: #666; text-align: center; '
                'line-height: 1.4;">'
            )
            if caption:
                figure_html += caption
            if credit:
                if caption:
                    figure_html += '<br/>'
                figure_html += f'<em>{credit}</em>'
            figure_html += '</div>'

        figure_html += '\n    </div>\n</div>'
        return figure_html

    def _create_cover_page(self) -> Optional[epub.EpubCover]:
        """Create cover page chapter for the EPUB.

        Returns:
            EpubCover instance or None if no cover data.
        """
        if not self.full_res_cover_data:
            return None

        print("\nCreating cover page...")

        # Add full resolution cover image
        cover_img = epub.EpubItem(
            uid='cover_page_image',
            file_name='images/cover_full.jpg',
            media_type='image/jpeg'
        )
        cover_img.content = self.full_res_cover_data
        self.book.add_item(cover_img)

        # Create cover page
        cover_chapter = epub.EpubCover(
            uid='cover-page',
            file_name='cover_page.xhtml'
        )
        cover_chapter.content = COVER_PAGE_HTML
        self.book.add_item(cover_chapter)

        # Add guide reference
        self.book.guide = [{
            'type': 'cover',
            'title': 'Cover',
            'href': 'cover_page.xhtml'
        }]

        print("  ✓ Cover page created")
        return cover_chapter

    def _build_table_of_contents(self) -> List:
        """Build hierarchical table of contents.

        Returns:
            List of TOC entries.
        """
        toc = []

        for section in SECTION_ORDER:
            if section in self.sections and self.sections[section]:
                section_chapters = self._sort_section_chapters(
                    section, self.sections[section]
                )
                toc.append((
                    epub.Section(section),
                    tuple(section_chapters)
                ))

        if 'Other' in self.sections and self.sections['Other']:
            toc.append((
                epub.Section('Other'),
                tuple(self.sections['Other'])
            ))

        return toc

    def _sort_section_chapters(
        self, section: str, chapters: List
    ) -> List:
        """Sort chapters within a section (WTW: Politics → Business → Cartoon)."""
        if section != 'The world this week':
            return chapters

        from utils import wtw_subsection_sort_key

        def chapter_key(chapter) -> tuple:
            url = getattr(chapter, 'article_url', '') or ''
            return (wtw_subsection_sort_key(url), chapter.title or '')

        return sorted(chapters, key=chapter_key)

    def _add_stylesheet(self) -> None:
        """Add CSS stylesheet to the EPUB."""
        css = epub.EpubItem(
            uid="style",
            file_name="style.css",
            media_type="text/css",
            content=EPUB_STYLESHEET
        )
        self.book.add_item(css)

    def _print_summary(self, output_file: Path,
                       edition: Edition) -> None:
        """Print summary of generated EPUB.

        Args:
            output_file: Path to generated EPUB file.
            edition: Edition information.
        """
        file_size = os.path.getsize(output_file)
        file_size_mb = file_size / (1024 * 1024)

        num_sections = len([s for s in self.sections if self.sections[s]])

        # Estimate page count
        total_paragraphs = sum(
            content.count('<p>') for content in
            [ch.content for ch in self.chapters]
        )
        estimated_pages = max(1, total_paragraphs // 2)

        print("\n" + "=" * 60)
        print("✅ EPUB CREATED SUCCESSFULLY!")
        print("=" * 60)
        print(f"📖 Edition: {edition.title}")
        print(f"📚 Articles: {len(self.chapters)}")
        print(f"📑 Sections: {num_sections}")
        print(f"📄 Est. Pages: ~{estimated_pages}")
        print(f"🖼️  Images: {self.image_handler.images_added}")
        print(f"💾 File Size: {file_size_mb:.2f} MB")
        print(f"📁 Location: {output_file}")
        print("=" * 60)
