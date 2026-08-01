#!/usr/bin/env python3
"""The Economist EPUB Generator - Main entry point.

This module orchestrates the scraping and EPUB generation process.

Typical usage:
    python src/main.py
    python src/main.py --limit 10 --debug
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.epub_builder import EpubBuilder  # noqa: E402
from src.scraper import EconomistScraper  # noqa: E402
from src.utils import create_directories  # noqa: E402


def main() -> None:
    """Main entry point for the EPUB generator."""
    parser = argparse.ArgumentParser(
        description='Generate EPUB from The Economist CURRENT weekly edition only',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s                     # Process all articles from current edition
  %(prog)s --limit 10          # Process only first 10 articles from current edition
  %(prog)s --until-section Leaders  # Stop after Leaders section
  %(prog)s --debug --limit 5   # Debug mode with 5 articles from current edition

NOTE: This tool only downloads the CURRENT weekly edition.
Targeting specific past editions is not supported by design.
        '''
    )

    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode (saves HTML files)'
    )

    parser.add_argument(
        '--limit',
        type=int,
        metavar='N',
        help='Limit number of articles to process (e.g., --limit 10)'
    )

    parser.add_argument(
        '--until-section',
        type=str,
        metavar='NAME',
        help='Scrape through this section inclusive (e.g. Leaders), then stop'
    )

    args = parser.parse_args()

    if args.limit is not None and args.limit <= 0:
        print("Error: --limit must be a positive number")
        sys.exit(1)

    # Create necessary directories
    create_directories(debug=args.debug)

    # Initialize components
    scraper = EconomistScraper(debug=args.debug)
    builder = EpubBuilder(debug=args.debug)

    try:
        print("\n" + "=" * 60)
        print("The Economist EPUB Generator")
        print("=" * 60 + "\n")

        # Initialize browser and authenticate
        scraper.initialize()

        # Scrape weekly edition for article links
        edition = scraper.scrape_weekly_edition()

        if not edition.articles:
            print("No articles found!")
            return

        # Scrape article content
        successful_articles = scraper.scrape_articles(
            limit=args.limit,
            until_section=args.until_section,
        )

        if not successful_articles:
            print("No articles successfully scraped!")
            return

        # Build EPUB
        output_file = builder.build(edition, successful_articles)

        print(f"\n✅ Success! EPUB saved to: {output_file}")

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except PermissionError as e:
        print(f"\n\nPermission error: {e}")
        print("Please check file/directory permissions")
        sys.exit(1)
    except ImportError as e:
        print(f"\n\nMissing dependency: {e}")
        print("Please run: uv sync")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)
    finally:
        # Clean up
        try:
            scraper.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    main()
