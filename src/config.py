"""Configuration and constants for the Economist EPUB generator."""

import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

ECONOMIST_EMAIL = os.getenv("ECONOMIST_EMAIL", "").strip()
ECONOMIST_PASSWORD = os.getenv("ECONOMIST_PASSWORD", "").strip()

# URLs
# IMPORTANT: This URL always points to the CURRENT weekly edition only.
# The tool intentionally does not support targeting specific past editions
# to prevent abuse and respect The Economist's content distribution model.
ECONOMIST_URL = (
  "https://www.economist.com/weeklyedition"  # Current edition only
)
LOGIN_URL = "https://www.economist.com/api/auth/login"

# The Economist sections in standard order
SECTION_ORDER: List[str] = [
  "The world this week",
  "Leaders",
  "Letters",
  "By Invitation",
  "Briefing",
  "United States",
  "The Americas",
  "Asia",
  "China",
  "Middle East & Africa",
  "Europe",
  "Britain",
  "International",
  "Business",
  "Finance & economics",
  "Science & technology",
  "Culture",
  "Economic & financial indicators",
  "Obituary",
]

# Subsection order within "The world this week"
WTW_SUBSECTION_ORDER = ["politics", "business", "cartoon"]

# Content filtering patterns
SKIP_PHRASES: List[str] = [
  "sign up",
  "subscribe",
  "newsletter",
  "download the app",
  "this article appeared",
  "from the print edition",
  "reuse this content",
  "more from",
  "also in this",
  "listen to this story",
  "enjoy more audio",
]

# Image filtering patterns
IMAGE_SKIP_PATTERNS: List[str] = ["pixel", "beacon", "track", ".gif"]
COVER_PATTERNS: List[str] = ["_DE_", "_FH", "cover"]

# Processing limits
MIN_PARAGRAPH_LENGTH = 40
MAX_IMAGES_PER_ARTICLE = 3

# Image settings
IMAGE_QUALITY = 95
COVER_IMAGE_QUALITY = 100
COVER_IMAGE_WIDTH = 800
COVER_IMAGE_HEIGHT = 1200
HIGH_RES_IMAGE_WIDTH = 1424
IMAGE_QUALITY_STANDARD = 80

# Browser settings
PAGE_LOAD_WAIT_TIME = 5
ARTICLE_LOAD_WAIT_TIME = 3
ARTICLE_FETCH_COOLDOWN = 3

# File paths
OUTPUT_DIR = "ebooks"
DEBUG_DIR = "debug"
LOGS_DIR = "logs"

# User agent for requests
USER_AGENT = (
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
)

# Month names mapping
MONTH_NAMES = {
  "01": "January",
  "02": "February",
  "03": "March",
  "04": "April",
  "05": "May",
  "06": "June",
  "07": "July",
  "08": "August",
  "09": "September",
  "10": "October",
  "11": "November",
  "12": "December",
}

# Inverse mapping for month names to numbers
MONTH_NUMBERS = {
  "January": "01",
  "February": "02",
  "March": "03",
  "April": "04",
  "May": "05",
  "June": "06",
  "July": "07",
  "August": "08",
  "September": "09",
  "October": "10",
  "November": "11",
  "December": "12",
}

# CSS stylesheet for EPUB
EPUB_STYLESHEET = """
@namespace epub "http://www.idpf.org/2007/ops";
body {
    font-family: Georgia, serif;
    line-height: 1.6;
    margin: 1em;
    max-width: 40em;
    margin-left: auto;
    margin-right: auto;
}
.image-container {
    width: 100%;
    max-width: 100%;
    margin: 0;
    padding: 0;
}
h1 {
    font-size: 1.8em;
    margin-bottom: 0.5em;
}
h2 {
    font-size: 1.4em;
    margin-top: 1em;
}
h3 {
    font-size: 1.2em;
    margin-top: 0.8em;
}
p {
    margin: 1em 0;
    text-align: justify;
}
img {
    width: 100% !important;
    height: auto !important;
    display: block !important;
    margin: 0 !important;
    padding: 0 !important;
}
div.image-container {
    width: 100% !important;
    margin: 1.5em 0 !important;
    padding: 0 !important;
    text-align: center !important;
    page-break-inside: avoid !important;
}
div.image-wrapper {
    width: 90% !important;
    margin-left: 5% !important;
    margin-right: 5% !important;
}
div.image-caption {
    margin-top: 0.5em !important;
    font-size: 0.9em !important;
    color: #666 !important;
    text-align: center !important;
    line-height: 1.4 !important;
}
"""

# Cover page HTML template
COVER_PAGE_HTML = """
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>Cover</title>
    <style type="text/css">
        @page {
            margin: 0 !important;
            padding: 0 !important;
        }
        html, body {
            margin: 0 !important;
            padding: 0 !important;
            width: 100% !important;
            height: 100% !important;
            overflow: hidden !important;
        }
        body {
            display: flex !important;
            justify-content: center !important;
            align-items: center !important;
            background: #000 !important;
        }
        img {
            width: 100% !important;
            height: 100% !important;
            max-width: 100% !important;
            max-height: 100% !important;
            object-fit: contain !important;
            display: block !important;
            margin: 0 !important;
            padding: 0 !important;
        }
    </style>
</head>
<body>
    <img src="cover.jpg" alt="The Economist Cover"/>
</body>
</html>
"""
