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
from hypothesis_log import PROBE, asset_key
from models import Article
from utils import (
    EditionParseError, SKIP_SECTION_HEADINGS, convert_symbols,
    is_valid_article_url,
)


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
        PROBE.article_start(url or '', article.title, None)
        PROBE.fetch_quality(url or '', html)

        # Extract title
        h1 = soup.find('h1')
        if h1:
            article.title = h1.get_text(' ', strip=True)

        # Extract subtitle
        article.subtitle = self._extract_subtitle(soup)

        # Extract hero image
        hero_url, hero_source = self._extract_hero_image(html)
        if hero_url and hero_url not in self.seen_image_urls:
            if not any(skip in hero_url for skip in IMAGE_SKIP_PATTERNS):
                near = PROBE.near_dupe_lookup(hero_url, self.seen_image_urls)
                article.add_image(
                    src=hero_url,
                    is_hero=True
                )
                self.seen_image_urls.add(hero_url)
                PROBE.hero_extracted(
                    url or '', hero_url, hero_source, accepted=True,
                    reason=f'near_dupe_of={near}' if near else None,
                )
            else:
                PROBE.hero_extracted(
                    url or '', hero_url, hero_source, accepted=False,
                    reason='skip_pattern',
                )
        elif hero_url:
            near = PROBE.near_dupe_lookup(hero_url, self.seen_image_urls)
            PROBE.hero_extracted(
                url or '', hero_url, hero_source, accepted=False,
                reason='exact_seen' + (f';near={near}' if near else ''),
            )
        else:
            PROBE.hero_extracted(
                url or '', None, None, accepted=False, reason='not_found',
            )

        # Find and process article body
        article_body, body_selector = self._find_article_body(soup)
        self._log_body_scope(soup, article_body, body_selector, url or '')

        for element in self._iter_content_elements(article_body):
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
                self._process_figure(
                    element, article, url, article_body=article_body,
                )

        PROBE.article_summary(
            url or '',
            article.title,
            article.image_count,
            article.paragraph_count,
        )
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

    ECONOMIST_BASE_URL = 'https://www.economist.com'

    def extract_edition_articles(self, html: str) -> List[dict]:
        """Extract article links from weekly edition page in DOM order.

        Walks <main> in document order: h2 headings set the section, h3>a and
        standalone article links are collected under the current section.

        Args:
            html: Weekly edition page HTML.

        Returns:
            List of article dicts with title, url, and section in page order.

        Raises:
            EditionParseError: When the page structure cannot be parsed.
        """
        soup = BeautifulSoup(html, 'html.parser')
        main = soup.find('main', id='content') or soup.find('main')
        if main is None:
            raise EditionParseError(
                'no_main_element',
                'Weekly edition page has no <main> element.',
            )

        current_section: Optional[str] = None
        section_headings: List[str] = []
        articles: List[dict] = []
        seen_urls: set[str] = set()

        for element in main.find_all(['h2', 'h3', 'a']):
            if element.name == 'h2':
                heading = element.get_text(' ', strip=True)
                if not heading or heading in SKIP_SECTION_HEADINGS:
                    continue
                current_section = heading
                section_headings.append(heading)
                continue

            anchor = None
            if element.name == 'h3':
                anchor = element.find('a', href=True)
            elif element.name == 'a' and element.find_parent('h3') is None:
                anchor = element if element.get('href') else None

            if anchor is None:
                continue

            href = anchor.get('href', '')
            text = anchor.get_text(' ', strip=True)
            if not is_valid_article_url(href, text):
                continue

            if current_section is None:
                raise EditionParseError(
                    'article_without_section',
                    f'Article link before first section heading: {href}',
                )

            if not href.startswith('http'):
                href = urljoin(self.ECONOMIST_BASE_URL, href)

            if href in seen_urls:
                continue
            seen_urls.add(href)

            articles.append({
                'title': text,
                'url': href,
                'section': current_section,
            })

        if not section_headings:
            raise EditionParseError(
                'no_section_headings',
                'No section headings found in weekly edition <main>.',
            )

        if not articles:
            raise EditionParseError(
                'no_articles_found',
                f'Found {len(section_headings)} sections but no article links.',
            )

        return articles

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

    def _extract_hero_image(
        self, html: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Extract hero/banner image URL from article HTML.

        Returns:
            (url, source) where source is 'preload', 'video_poster',
            'og:image', or None.
        """
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
                        return hero_url, 'preload'

        # Interactive articles often use a hero <video poster="...">
        for video in soup.find_all('video'):
            poster = video.get('poster')
            if poster and self._is_valid_hero_image(poster):
                if self.debug:
                    print(f"    Found hero from video poster: "
                          f"{poster.split('/')[-1][:40]}...")
                return poster, 'video_poster'

        # Fallback to meta og:image
        og_image = soup.find('meta', {'property': 'og:image'})
        if og_image:
            content = og_image.get('content')
            if content and not any(p in content for p in COVER_PATTERNS):
                if self.debug:
                    print(f"    Found hero from og:image: "
                          f"{content.split('/')[-1][:40]}...")
                return content, 'og:image'

        return None, None

    def _is_valid_hero_image(self, url: str) -> bool:
        """Check if URL is a valid hero image."""
        if any(pattern in url for pattern in COVER_PATTERNS):
            if re.search(r'_[A-Z]{3}\d{3}\.', url) and '_DE_' not in url:
                return True
            return False
        return True

    def _find_article_body(
        self, soup: BeautifulSoup
    ) -> Tuple[BeautifulSoup, str]:
        """Find the main article body container.

        Returns:
            (body_element, selector_label)
        """
        selectors = [
            ('data-component=article-body',
             {'name': 'div', 'attrs': {'data-component': 'article-body'}}),
            ('itemprop=articleBody',
             {'name': 'div', 'attrs': {'itemprop': 'articleBody'}}),
            ('article#new-article-template',
             {'name': 'article', 'attrs': {'id': 'new-article-template'}}),
            ('article',
             {'name': 'article', 'attrs': {}}),
            ('section.ei2yr3n0',
             {'name': 'section',
              'attrs': {'class': re.compile('ei2yr3n0')}}),
            ('main#content',
             {'name': 'main', 'attrs': {'id': 'content'}}),
            ('main[role=main]',
             {'name': 'main', 'attrs': {'role': 'main'}}),
        ]

        for label, selector in selectors:
            article_body = soup.find(
                selector['name'],
                selector.get('attrs', {})
            )
            if article_body:
                return article_body, label

        return soup, 'soup'

    def _iter_content_elements(self, article_body):
        """Yield article content nodes, stopping at related-article chrome.

        Economist pages append a "More from <Section>" block inside <article>
        whose figures are other articles' heroes. Stop before that block.
        """
        for element in article_body.find_all(
            ['p', 'figure', 'body-text', 'h2']
        ):
            if element.name == 'h2':
                heading = element.get_text(' ', strip=True).lower()
                if heading.startswith('more from'):
                    PROBE.log(
                        'content_truncated',
                        hypothesis=['H1', 'H6'],
                        reason='more_from_heading',
                        heading=element.get_text(' ', strip=True),
                    )
                    return
                continue
            yield element

    def _log_body_scope(
        self,
        soup: BeautifulSoup,
        article_body,
        body_selector: str,
        url: str,
    ) -> None:
        """Log figure counts inside body vs whole main (H1/H6)."""
        main = soup.find('main', id='content') or soup.find('main') or soup
        body_figures = article_body.find_all('figure')
        main_figures = main.find_all('figure')
        body_ids = {id(f) for f in body_figures}
        outside = []
        for fig in main_figures:
            if id(fig) in body_ids:
                continue
            src = self._figure_src(fig)
            outside.append({
                'src': src,
                'asset': asset_key(src),
                'parent_hint': self._figure_parent_hint(fig),
                'caption': (fig.find('figcaption').get_text(' ', strip=True)
                            if fig.find('figcaption') else None),
            })

        more_from = None
        for h2 in article_body.find_all('h2'):
            if h2.get_text(' ', strip=True).lower().startswith('more from'):
                more_from = h2
                break
        after_more = []
        if more_from is not None:
            descendants = list(article_body.descendants)
            try:
                more_i = descendants.index(more_from)
            except ValueError:
                more_i = None
            if more_i is not None:
                for fig in body_figures:
                    try:
                        fi = descendants.index(fig)
                    except ValueError:
                        continue
                    if fi > more_i:
                        src = self._figure_src(fig)
                        after_more.append({
                            'src': src,
                            'asset': asset_key(src),
                        })

        PROBE.body_scope(
            url,
            body_selector,
            figures_in_body=len(body_figures),
            figures_in_main=len(main_figures),
            figures_outside_body=outside,
        )
        PROBE.log(
            'more_from_figures',
            hypothesis=['H1', 'H6'],
            url=url,
            selector=body_selector,
            more_from_present=more_from is not None,
            figures_after_more_from=after_more,
            h1_suspect=len(after_more) > 0,
        )

    def _figure_src(self, element) -> Optional[str]:
        """Get image URL from a figure (img src or video poster)."""
        img = element.find('img')
        if img and img.get('src'):
            return img.get('src')
        video = element.find('video')
        if video and video.get('poster'):
            return video.get('poster')
        return None

    def _figure_parent_hint(self, element) -> str:
        """Summarize parent context for a figure element."""
        bits = []
        for parent in element.parents:
            if parent.name in (None, '[document]'):
                break
            dc = parent.get('data-component') if hasattr(parent, 'get') else None
            if dc:
                bits.append(f'comp={dc}')
            pid = parent.get('id') if hasattr(parent, 'get') else None
            if pid:
                bits.append(f'id={pid}')
            if len(bits) >= 4:
                break
        return '>'.join(bits) if bits else element.name or 'unknown'

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
                        page_url: Optional[str] = None,
                        article_body=None) -> None:
        """Process and add figure element to article content."""
        src = self._figure_src(element)
        if not src:
            return

        if src and not src.startswith('http'):
            base = page_url or 'https://www.economist.com'
            src = urljoin(base, src)

        caption_text, credit_text = self._extract_caption_credit(element)
        parent_hint = self._figure_parent_hint(element)
        inside_body = True
        if article_body is not None:
            inside_body = any(
                p is article_body for p in element.parents
            ) or element is article_body
        paragraph_index_before = article.paragraph_count
        block_index = len(article.content_blocks)
        near = PROBE.near_dupe_lookup(src, self.seen_image_urls)
        exact_seen = src in self.seen_image_urls

        # Skip malicious URLs
        if any(pattern in src.lower() for pattern in
               ['javascript:', 'data:', 'vbscript:']):
            PROBE.figure_candidate(
                page_url or '', src, accepted=False, reason='malicious',
                caption=caption_text, parent_hint=parent_hint,
                inside_article_body=inside_body, block_index=block_index,
                paragraph_index_before=paragraph_index_before,
                near_dupe_of=near, exact_seen=exact_seen,
            )
            return

        # Skip invalid images
        if any(pattern in src for pattern in
               COVER_PATTERNS + IMAGE_SKIP_PATTERNS):
            PROBE.figure_candidate(
                page_url or '', src, accepted=False, reason='skip_pattern',
                caption=caption_text, parent_hint=parent_hint,
                inside_article_body=inside_body, block_index=block_index,
                paragraph_index_before=paragraph_index_before,
                near_dupe_of=near, exact_seen=exact_seen,
            )
            return

        if exact_seen:
            PROBE.figure_candidate(
                page_url or '', src, accepted=False, reason='exact_seen',
                caption=caption_text, parent_hint=parent_hint,
                inside_article_body=inside_body, block_index=block_index,
                paragraph_index_before=paragraph_index_before,
                near_dupe_of=near, exact_seen=True,
            )
            return

        article.add_image(
            src=src,
            caption=caption_text,
            credit=credit_text
        )
        self.seen_image_urls.add(src)
        PROBE.figure_candidate(
            page_url or '', src, accepted=True,
            reason='near_dupe' if near else 'ok',
            caption=caption_text, parent_hint=parent_hint,
            inside_article_body=inside_body, block_index=block_index,
            paragraph_index_before=paragraph_index_before,
            near_dupe_of=near, exact_seen=False,
        )

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
