"""Tests for Belgium pipeline data models and validation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from belgium.models import (
    BelgiumArticle,
    Shortlist,
    SourceArticle,
    SourceIndex,
    validate_article,
    validate_shortlist,
)


class TestSourceIndex(unittest.TestCase):
    """SourceIndex round-trip."""

    def test_save_load(self) -> None:
        index = SourceIndex(
            fetched_at="2026-09-19T12:00:00Z",
            days=7,
            articles=[
                SourceArticle(
                    title="Test",
                    url="https://www.vrt.be/vrtnws/nl/2026/09/19/test/",
                    published="2026-09-19T10:00:00Z",
                    category="Binnenland",
                    body="Hello",
                )
            ],
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.json"
            index.save(path)
            loaded = SourceIndex.load(path)
        self.assertEqual(loaded.days, 7)
        self.assertEqual(len(loaded.articles), 1)
        self.assertEqual(loaded.articles[0].title, "Test")


class TestShortlistValidation(unittest.TestCase):
    """Shortlist schema validation."""

    def test_valid_shortlist(self) -> None:
        data = {
            "topics": [
                {
                    "slug": "nuclear-restart",
                    "working_hed": "Belgium's nuclear gamble",
                    "why_economist": "Energy security meets politics.",
                    "source_urls": ["https://www.vrt.be/vrtnws/nl/example/"],
                    "confidence": 0.8,
                }
            ]
        }
        self.assertEqual(validate_shortlist(data), [])
        shortlist = Shortlist.from_dict(data)
        self.assertEqual(shortlist.topics[0].slug, "nuclear-restart")

    def test_rejects_empty_topics(self) -> None:
        errors = validate_shortlist({"topics": []})
        self.assertTrue(any("at least one" in e for e in errors))

    def test_rejects_missing_why(self) -> None:
        data = {
            "topics": [
                {
                    "slug": "x",
                    "working_hed": "Hed",
                    "why_economist": "",
                    "source_urls": ["https://example.com"],
                    "confidence": 0.5,
                }
            ]
        }
        errors = validate_shortlist(data)
        self.assertTrue(any("why_economist" in e for e in errors))


class TestArticleValidation(unittest.TestCase):
    """BelgiumArticle schema validation."""

    def _long_paragraphs(self, n: int = 6) -> list:
        # ~80 words each → enough for the 200-word floor
        sentence = (
            "Belgium remains an awkward middle power in European politics, "
            "balancing Flemish and Walloon interests while hosting EU institutions "
            "that increasingly set the agenda for energy and fiscal policy. "
        )
        return [sentence * 2 for _ in range(n)]

    def test_valid_article(self) -> None:
        data = {
            "title": "A nuclear rethink",
            "subtitle": "Belgium looks again at reactors",
            "slug": "nuclear-rethink",
            "section": "Belgium",
            "paragraphs": self._long_paragraphs(),
            "sources": [
                {
                    "title": "VRT piece",
                    "url": "https://www.vrt.be/vrtnws/nl/example/",
                    "publisher": "VRT NWS",
                }
            ],
            "topic_rationale": "Energy policy with EU stakes.",
        }
        self.assertEqual(validate_article(data), [])
        article = BelgiumArticle.from_dict(data)
        self.assertEqual(article.section, "Belgium")
        md = article.to_markdown()
        self.assertIn("# A nuclear rethink", md)
        self.assertIn("*Belgium looks again at reactors*", md)
        self.assertIn("## Sources", md)

    def test_rejects_short_body(self) -> None:
        data = {
            "title": "Too short",
            "slug": "too-short",
            "section": "Belgium",
            "paragraphs": ["One.", "Two.", "Three."],
            "sources": [{"title": "A", "url": "https://example.com"}],
            "topic_rationale": "Because.",
        }
        errors = validate_article(data)
        self.assertTrue(any("too short" in e for e in errors))

    def test_rejects_wrong_section(self) -> None:
        data = {
            "title": "Title",
            "slug": "title",
            "section": "Europe",
            "paragraphs": self._long_paragraphs(),
            "sources": [{"title": "A", "url": "https://example.com"}],
            "topic_rationale": "Because.",
        }
        errors = validate_article(data)
        self.assertTrue(any("Belgium" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
