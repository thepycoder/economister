"""Tests for VRT NWS client parsing (offline fixtures)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from belgium.vrt_client import (
    VrtClient,
    VrtNwsError,
    collect_week,
    extract_summaries,
    html_to_text,
    parse_article,
    write_source_pack,
)
from belgium.models import SourceIndex

TEST_DATA = Path(__file__).resolve().parent / "test_data"


class TestHtmlToText(unittest.TestCase):
    """HTML flattening."""

    def test_paragraphs(self) -> None:
        html = "<p>First</p><p>Second</p>"
        self.assertEqual(html_to_text(html), "First\n\nSecond")

    def test_plain(self) -> None:
        self.assertEqual(html_to_text("Just text"), "Just text")


class TestExtractSummaries(unittest.TestCase):
    """Listing teaser extraction."""

    def test_minimal_listing(self) -> None:
        payload = json.loads(
            (TEST_DATA / "listing_minimal.json").read_text(encoding="utf-8")
        )
        items = extract_summaries(payload)
        self.assertGreaterEqual(len(items), 1)
        self.assertTrue(items[0]["title"])
        self.assertIn("vrt.be", items[0]["url"])

    def test_empty_payload_raises_via_collect(self) -> None:
        client = MagicMock(spec=VrtClient)
        client.get_latest.side_effect = VrtNwsError("fail")
        client.get_section_page.side_effect = VrtNwsError("fail")
        with self.assertRaises(VrtNwsError):
            collect_week(days=7, client=client, fetch_bodies=False)


class TestParseArticle(unittest.TestCase):
    """Article body extraction from recorded BFF payload."""

    def test_recorded_article(self) -> None:
        payload = json.loads(
            (TEST_DATA / "article.json").read_text(encoding="utf-8")
        )
        url = (TEST_DATA / "article_url.txt").read_text(encoding="utf-8").strip()
        article = parse_article(payload, url)
        self.assertTrue(article.title)
        self.assertTrue(article.body)
        self.assertIn("Saudi", article.title)
        self.assertGreater(len(article.body.split()), 40)


class TestWriteSourcePack(unittest.TestCase):
    """On-disk source pack layout."""

    def test_writes_index_and_markdown(self) -> None:
        import tempfile

        index = SourceIndex(
            fetched_at="2026-09-19T12:00:00Z",
            days=7,
            articles=[],
        )
        from belgium.models import SourceArticle

        index.articles.append(
            SourceArticle(
                title="Example",
                url="https://www.vrt.be/vrtnws/nl/2026/09/19/example/",
                published="2026-09-19T10:00:00Z",
                category="Binnenland",
                body="Body text here.",
                slug="example",
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = write_source_pack(index, run_dir)
            self.assertTrue(path.exists())
            md = run_dir / "sources" / "articles" / "example.md"
            self.assertTrue(md.exists())
            self.assertIn("Body text here.", md.read_text(encoding="utf-8"))


class TestCollectWeekMocked(unittest.TestCase):
    """collect_week with mocked BFF responses."""

    def test_filters_and_builds_index(self) -> None:
        listing = json.loads(
            (TEST_DATA / "listing_minimal.json").read_text(encoding="utf-8")
        )
        # Force published timestamps into the lookback window.
        for node in listing["compositions"]:
            node["publication"] = {"timestamp": 1_774_000_000_000}

        article_payload = json.loads(
            (TEST_DATA / "article.json").read_text(encoding="utf-8")
        )
        article_url = (
            (TEST_DATA / "article_url.txt").read_text(encoding="utf-8").strip()
        )

        client = MagicMock(spec=VrtClient)
        client.get_latest.return_value = listing
        client.get_section_page.return_value = {"compositions": []}

        def read_article(url: str):
            from belgium.vrt_client import parse_article as _parse

            return _parse(article_payload, article_url)

        client.read_article.side_effect = read_article

        index = collect_week(days=3650, client=client, fetch_bodies=True, max_articles=3)
        self.assertGreaterEqual(len(index.articles), 1)
        self.assertTrue(index.articles[0].title)


if __name__ == "__main__":
    unittest.main()
