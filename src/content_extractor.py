"""Content extraction from HTML pages."""

import re
from copy import copy
from typing import List, Optional, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from config import (
    COVER_PATTERNS, IMAGE_SKIP_PATTERNS, MIN_PARAGRAPH_LENGTH,
    SKIP_PHRASES
)
from models import Article
from utils import convert_symbols


class ContentExtractor:
    """Extracts structured content from HTML."""

    def __init__(self, debug: bool = False):
        """Initialize content extractor.

        Args:
            debug: Enable debug output.
        """
        self.debug = debug
        self.seen_image_urls = set()
        self.cover_patterns = set()

    def extract_article(self, html: str, url: str = None) -> Article:
        """Extract structured content from article HTML.

        Args:
            html: Raw HTML content of the article.
            url: Article URL (optional).

        Returns:
            Article object with extracted content.
        """
        soup = BeautifulSoup(html, 'html.parser')
        article = Article(url=url)

        # Extract title
        h1 = soup.find('h1')
        if h1:
            article.title = h1.get_text(' ', strip=True)

        # Extract subtitle
        article.subtitle = self._extract_subtitle(soup)

        # Extract hero image
        hero_url = self._extract_hero_image(html)
        if hero_url and hero_url not in self.seen_image_urls:
            if not any(skip in hero_url for skip in IMAGE_SKIP_PATTERNS):
                article.add_image(
                    src=hero_url,
                    is_hero=True
                )
                self.seen_image_urls.add(hero_url)

        # Find and process article body
        article_body = self._find_article_body(soup)

        for element in article_body.find_all(['p', 'figure', 'body-text']):
            if element.name == 'body-text':
                if element.find_parent('figcaption'):
                    continue
                if not element.find_parent(
                    'div', class_=re.compile(r'article-text')
                ):
                    continue
                self._process_body_text(element, article)
            elif element.name == 'p':
                self._process_paragraph(element, article)
            elif element.name == 'figure':
                self._process_figure(element, article, url)

        return article

    def extract_cover_url(self, html: str) -> Optional[str]:
        """Extract cover image URL from page.

        Args:
            html: Page HTML.

        Returns:
            Cover image URL or None.
        """
        soup = BeautifulSoup(html, 'html.parser')

        for img in soup.find_all('img'):
            src = img.get('src', '')
            if '_DE_' in src or 'cover' in src.lower():
                return src

        return None

    def extract_article_links(self, html: str) -> List[dict]:
        """Extract article links from weekly edition page.

        Args:
            html: Page HTML.

        Returns:
            List of article info dictionaries.
        """
        from utils import is_valid_article_url, detect_section_from_url

        soup = BeautifulSoup(html, 'html.parser')
        articles = []
        seen_urls = set()

        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.get_text(' ', strip=True)

            if not is_valid_article_url(href, text):
                continue

            if not href.startswith('http'):
                href = urljoin('https://www.economist.com', href)

            if href not in seen_urls:
                seen_urls.add(href)
                articles.append({
                    'title': text,
                    'url': href,
                    'section': detect_section_from_url(href)
                })

        return articles

    def extract_world_this_week_links(self, html: str) -> List[dict]:
        """Extract WTW article links from the weekly edition page.

        Uses URL pattern matching so short anchor text ("Politics") is kept.
        """
        from utils import detect_section_from_url, is_world_this_week_url

        soup = BeautifulSoup(html, 'html.parser')
        links = []
        seen: set[str] = set()

        for anchor in soup.find_all('a', href=True):
            href = anchor.get('href', '')
            if not is_world_this_week_url(href):
                continue
            if not re.search(r'/202[4-9]/\d{2}/\d{2}/', href):
                continue

            if not href.startswith('http'):
                href = urljoin('https://www.economist.com', href)

            if href in seen:
                continue
            seen.add(href)

            text = anchor.get_text(' ', strip=True) or href.rstrip('/').split('/')[-1]
            links.append({
                'title': text,
                'url': href,
                'section': detect_section_from_url(href),
            })

        return links

    def merge_article_links(
        self, primary: List[dict], extra: List[dict]
    ) -> List[dict]:
        """Merge link lists, preferring entries from *extra* on URL collision."""
        by_url = {item['url']: item for item in primary}
        for item in extra:
            by_url[item['url']] = item
        return list(by_url.values())

    def _extract_subtitle(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract article subtitle/tagline from soup."""
        # Try h2 tags first
        for h2 in soup.find_all('h2'):
            classes = h2.get('class', [])
            if classes and any('e6h2z500' in c or 'fxcbca' in c
                               for c in classes):
                return h2.get_text(' ', strip=True)

        # Try p tags (older format)
        for p in soup.find_all('p'):
            classes = p.get('class', [])
            if classes and any('ykv9c9' in c for c in classes):
                return p.get_text(' ', strip=True)

        return None

    def _extract_hero_image(self, html: str) -> Optional[str]:
        """Extract hero/banner image URL from article HTML."""
        soup = BeautifulSoup(html, 'html.parser')

        # Try preload link first
        preload = soup.find('link', {'rel': 'preload', 'as': 'image'})
        if preload:
            srcset = preload.get('imagesrcset', '')
            if srcset:
                matches = re.findall(r'(https://[^\s]+)\s+(\d+)w', srcset)
                if matches:
                    sorted_urls = sorted(
                        matches, key=lambda x: int(x[1]), reverse=True
                    )
                    hero_url = sorted_urls[0][0] if sorted_urls else None

                    if hero_url and self._is_valid_hero_image(hero_url):
                        if self.debug:
                            resolution = sorted_urls[0][1]
                            filename = hero_url.split('/')[-1][:40]
                            print(f"    Found hero image: {resolution}w - "
                                  f"{filename}...")
                        return hero_url

        # Fallback to meta og:image
        og_image = soup.find('meta', {'property': 'og:image'})
        if og_image:
            content = og_image.get('content')
            if content and not any(p in content for p in COVER_PATTERNS):
                if self.debug:
                    print(f"    Found hero from og:image: "
                          f"{content.split('/')[-1][:40]}...")
                return content

        return None

    def _is_valid_hero_image(self, url: str) -> bool:
        """Check if URL is a valid hero image."""
        if any(pattern in url for pattern in COVER_PATTERNS):
            if re.search(r'_[A-Z]{3}\d{3}\.', url) and '_DE_' not in url:
                return True
            return False
        return True

    def _find_article_body(self, soup: BeautifulSoup) -> BeautifulSoup:
        """Find the main article body container."""
        selectors = [
            {'name': 'div', 'attrs': {'data-component': 'article-body'}},
            {'name': 'div', 'attrs': {'itemprop': 'articleBody'}},
            {'name': 'section',
             'attrs': {'class': re.compile('ei2yr3n0')}},
            {'name': 'main', 'attrs': {'id': 'content'}},
            {'name': 'main', 'attrs': {'role': 'main'}}
        ]

        for selector in selectors:
            article_body = soup.find(
                selector['name'],
                selector.get('attrs', {})
            )
            if article_body:
                return article_body

        return soup

    def _process_paragraph(self, element, article: Article) -> None:
        """Process and add paragraph element to article content."""
        classes = element.get('class', [])
        is_article_para = (
            (classes and any('1l5amll' in c or 'e1y9q0ei' in c
                             for c in classes)) or
            element.get('data-component') == 'paragraph'
        )

        if not is_article_para:
            return

        plain_text = element.get_text(' ', strip=True)
        plain_text = ' '.join(plain_text.split())

        # Filter out bad content
        if len(plain_text) < MIN_PARAGRAPH_LENGTH:
            return

        if any(phrase in plain_text.lower() for phrase in SKIP_PHRASES):
            return

        # Process HTML content
        inner_html = self._process_paragraph_html(element)
        article.add_paragraph(inner_html)

    def _process_paragraph_html(self, element) -> str:
        """Process paragraph HTML for proper formatting.

        Args:
            element: BeautifulSoup element to process.

        Returns:
            Sanitized and formatted HTML string.
        """
        p_copy = copy(element)

        # Remove any script or style tags
        for tag in p_copy.find_all(['script', 'style', 'iframe', 'object', 'embed']):
            tag.decompose()

        # Convert small caps to regular caps
        for small_tag in p_copy.find_all('small'):
            if small_tag.string:
                small_tag.string = small_tag.get_text().upper()
            small_tag.unwrap()

        # Handle drop caps
        for span in p_copy.find_all('span', {'data-caps': 'initial'}):
            span.unwrap()

        # Process text nodes and elements
        inner_parts = []
        for child in p_copy.children:
            if isinstance(child, str):
                # Keep text as-is (BeautifulSoup already handles escaping)
                inner_parts.append(str(child))
            else:
                # Only allow safe tags
                if child.name in ['em', 'strong', 'i', 'b', 'span']:
                    inner_parts.append(' ' + str(child) + ' ')
                elif child.name == 'a':
                    # Sanitize links
                    href = child.get('href', '')
                    if not any(p in href.lower() for p in
                               ['javascript:', 'data:', 'vbscript:']):
                        inner_parts.append(' ' + str(child) + ' ')
                    else:
                        inner_parts.append(child.get_text())
                else:
                    inner_parts.append(child.get_text())

        inner_html = ''.join(inner_parts)
        inner_html = re.sub(r'\s+', ' ', inner_html).strip()

        # Convert symbols to proper characters
        inner_html = convert_symbols(inner_html)

        return inner_html

    def _process_body_text(self, element, article: Article) -> None:
        """Process bespoke/interactive <body-text> prose blocks."""
        plain_text = element.get_text(' ', strip=True)
        plain_text = ' '.join(plain_text.split())

        if len(plain_text) < MIN_PARAGRAPH_LENGTH:
            return

        if any(phrase in plain_text.lower() for phrase in SKIP_PHRASES):
            return

        inner_html = self._process_paragraph_html(element)
        article.add_paragraph(inner_html)

    def _process_figure(self, element, article: Article,
                        page_url: Optional[str] = None) -> None:
        """Process and add figure element to article content."""
        img = element.find('img')
        if not img or not img.get('src'):
            return

        src = img.get('src')
        if src and not src.startswith('http'):
            base = page_url or 'https://www.economist.com'
            src = urljoin(base, src)

        # Skip malicious URLs
        if any(pattern in src.lower() for pattern in
               ['javascript:', 'data:', 'vbscript:']):
            return

        # Skip invalid images
        if any(pattern in src for pattern in
               COVER_PATTERNS + IMAGE_SKIP_PATTERNS):
            return

        if src in self.seen_image_urls:
            return

        # Extract caption and credit
        caption_text, credit_text = self._extract_caption_credit(element)

        article.add_image(
            src=src,
            caption=caption_text,
            credit=credit_text
        )
        self.seen_image_urls.add(src)

    def _extract_caption_credit(
        self, element
    ) -> Tuple[Optional[str], Optional[str]]:
        """Extract caption and credit text from figure element."""
        caption_text = None
        credit_text = None

        figcaption = element.find('figcaption')
        if not figcaption:
            return caption_text, credit_text

        full_caption = figcaption.get_text(' ', strip=True)
        full_caption = ' '.join(full_caption.split())

        credit_patterns = [
            r'(Illustration:.*?)(?:\.|$)',
            r'(Photo:.*?)(?:\.|$)',
            r'(Source:.*?)(?:\.|$)',
            r'(Chart:.*?)(?:\.|$)',
            r'(Credit:.*?)(?:\.|$)',
            r'(Image:.*?)(?:\.|$)'
        ]

        for pattern in credit_patterns:
            match = re.search(pattern, full_caption, re.IGNORECASE)
            if match:
                credit_text = match.group(1).strip()
                caption_text = full_caption.replace(
                    match.group(0), ''
                ).strip()
                break

        if not credit_text:
            caption_text = full_caption

        return caption_text, credit_text
