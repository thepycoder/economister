"""Utility functions for the Economist EPUB generator."""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import MONTH_NAMES, MONTH_NUMBERS


def create_directories(debug: bool = False) -> None:
    """Create necessary output directories.

    Args:
        debug: Whether to create debug directories.
    """
    Path('ebooks').mkdir(exist_ok=True)
    Path('logs').mkdir(exist_ok=True)
    if debug:
        Path('debug').mkdir(exist_ok=True)


def sanitize_filename(text: str, max_length: int = 50) -> str:
    """Sanitize text for use as filename.

    Args:
        text: Text to sanitize.
        max_length: Maximum length of result.

    Returns:
        Sanitized filename string.
    """
    if not text:
        return "untitled"

    # Remove dangerous characters and path traversal attempts
    text = text.replace('..', '').replace('/', '').replace('\\', '')

    # Keep only safe characters
    safe_text = re.sub(r'[^a-zA-Z0-9\s-]', '', text)[:max_length]
    safe_text = safe_text.strip()

    return safe_text if safe_text else "untitled"


def save_debug_html(title: str, html: str, debug: bool = False) -> None:
    """Save HTML content to debug file if debug mode is enabled.

    Args:
        title: Title for the debug file.
        html: HTML content to save.
        debug: Whether debug mode is enabled.
    """
    if not debug:
        return

    timestamp = datetime.now().strftime('%H%M%S')
    safe_title = sanitize_filename(title)
    filename = Path('debug') / f"{timestamp}_{safe_title}.html"

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"  Debug saved: {filename.name}")


def convert_symbols(text: str) -> str:
    """Convert text symbols to proper Unicode characters.

    Args:
        text: Text containing symbols to convert.

    Returns:
        Text with converted symbols.
    """
    text = re.sub(r'(?<=[a-zA-Z0-9])TM\b', '™', text)
    text = re.sub(r'\(TM\)', '™', text)
    text = re.sub(r'\(R\)', '®', text)
    text = re.sub(r'Copyright \(C\)', 'Copyright ©', text,
                  flags=re.IGNORECASE)
    text = re.sub(r'\(C\) (\d{4})', r'© \1', text)
    return text


def parse_edition_date(date_str: Optional[str]) -> tuple[str, str]:
    """Parse edition date string into formatted title and ID.

    Args:
        date_str: Date string in YYYY-MM-DD format or None.

    Returns:
        Tuple of (formatted_title, edition_id).
    """
    if date_str:
        year, month, day = date_str.split('-')
        month_name = MONTH_NAMES.get(month, month)
        title = f"The Economist - {month_name} {int(day)}, {year}"
        edition_id = f"economist-{year}{month}{day}"
    else:
        date_str = datetime.now().strftime('%Y-%m-%d')
        title = f"The Economist - {datetime.now().strftime('%B %d, %Y')}"
        edition_id = 'economist-' + datetime.now().strftime('%Y%m%d')

    return title, edition_id


def extract_date_from_cover_url(url: str) -> Optional[str]:
    """Extract date from cover image URL pattern.

    Args:
        url: Cover image URL.

    Returns:
        Date string in YYYY-MM-DD format or None.
    """
    match = re.search(r'/(\d{8})_', url)
    if match:
        date_pattern = match.group(1)
        year = date_pattern[:4]
        month = date_pattern[4:6]
        day = date_pattern[6:8]
        return f"{year}-{month}-{day}"
    return None


def extract_date_from_text(html: str) -> Optional[str]:
    """Extract edition date from page text.

    Args:
        html: Raw HTML content to search for dates.

    Returns:
        Date string in YYYY-MM-DD format or None.
    """
    pattern = (r'(January|February|March|April|May|June|July|August|'
               r'September|October|November|December)\s+'
               r'(\d{1,2})(?:st|nd|rd|th)?\s+(\d{4})')

    date_matches = re.findall(pattern, html)
    if date_matches:
        month_name, day, year = date_matches[0]
        month = MONTH_NUMBERS.get(month_name)
        if month:
            return f"{year}-{month}-{day.zfill(2)}"

    return None


def is_world_this_week_url(href: str) -> bool:
    """Return True if URL is a weekly 'The world this week' article."""
    return isinstance(href, str) and '/the-world-this-week/' in href


def wtw_subsection_sort_key(url: str) -> int:
    """Sort key for WTW articles: Politics → Business → Cartoon."""
    if not url:
        return 99
    slug = url.rstrip('/').split('/')[-1].lower()
    if slug == 'politics':
        return 0
    if slug == 'business':
        return 1
    if slug.startswith('cartoon'):
        return 2
    return 50


def is_valid_article_url(href: str, text: str) -> bool:
    """Check if URL is a valid article link.

    Args:
        href: URL to validate.
        text: Link text.

    Returns:
        True if URL is a valid article link.
    """
    if not href or not isinstance(href, str):
        return False

    if not text or not isinstance(text, str):
        return False

    # WTW TOC links use short labels ("Politics", "Business")
    if not is_world_this_week_url(href) and len(text) <= 10:
        return False

    # Validate URL format
    if not re.search(r'/202[4-9]/\d{2}/\d{2}/', href):
        return False

    # Check for malicious patterns
    if any(pattern in href.lower() for pattern in
           ['javascript:', 'data:', 'vbscript:']):
        return False

    skip_patterns = [
        '/podcasts/', '/films/',
        '/graphic-detail/', '/weeklyedition', '/newsletters'
    ]

    return not any(skip in href for skip in skip_patterns)


def detect_section_from_url(url: str) -> str:
    """Determine article section from URL pattern.

    Args:
        url: Article URL.

    Returns:
        Section name string.
    """
    url_patterns = {
        '/the-world-this-week/': 'The world this week',
        '/leaders/': 'Leaders',
        '/letters/': 'Letters',
        '/by-invitation/': 'By Invitation',
        '/briefing/': 'Briefing',
        '/united-states/': 'United States',
        '/the-americas/': 'The Americas',
        '/asia/': 'Asia',
        '/china/': 'China',
        '/middle-east-and-africa/': 'Middle East & Africa',
        '/europe/': 'Europe',
        '/britain/': 'Britain',
        '/international/': 'International',
        '/business/': 'Business',
        '/finance-and-economics/': 'Finance & economics',
        '/science-and-technology/': 'Science & technology',
        '/culture/': 'Culture',
        '/economic-and-financial-indicators/':
            'Economic & financial indicators',
        '/obituary/': 'Obituary'
    }

    for pattern, section in url_patterns.items():
        if pattern in url:
            return section

    return 'Other'
