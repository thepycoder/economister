"""Tests for the optional Belgium EPUB hook."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from belgium.epub import (
    briefing_window_start,
    collect_belgium_epub_articles,
    run_is_fresh,
    shortlist_is_written,
    to_epub_article,
    try_attach_belgium_articles,
)
from belgium.models import BelgiumArticle


def _piece(slug: str = "grid") -> BelgiumArticle:
    return BelgiumArticle.from_dict({
        "title": "Belgium's grid <test>",
        "subtitle": "A dek",
        "slug": slug,
        "section": "Belgium",
        "paragraphs": ["First <b>paragraph</b>.", "Second paragraph."],
        "sources": [{
            "title": "VRT",
            "url": "https://www.vrt.be/example",
            "publisher": "VRT NWS",
        }],
        "topic_rationale": "Energy.",
    })


class TestBelgiumEpub(unittest.TestCase):
    """Conversion and non-blocking attach behaviour."""

    def test_to_epub_article(self) -> None:
        article = to_epub_article(_piece())
        self.assertEqual(article.section, "Belgium")
        self.assertEqual(article.title, "Belgium's grid <test>")
        self.assertIn("First &lt;b&gt;paragraph&lt;/b&gt;.", article.content_blocks[0].content)
        self.assertEqual(article.paragraph_count, 3)
        self.assertIn("vrt.be/example", article.content_blocks[-1].content)

    def test_collect_uses_written_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "articles").mkdir()
            _piece().save(run_dir / "articles" / "grid.json")
            (run_dir / "shortlist.json").write_text(
                json.dumps({
                    "topics": [{
                        "slug": "grid",
                        "working_hed": "Grid",
                        "why_economist": "Energy.",
                        "source_urls": ["https://www.vrt.be/example"],
                        "confidence": 0.9,
                    }]
                }),
                encoding="utf-8",
            )
            self.assertTrue(shortlist_is_written(run_dir))

            def boom(**kwargs):
                raise AssertionError("should not generate")

            articles = collect_belgium_epub_articles(
                generate=True,
                run_dir=run_dir,
                writer_fn=boom,
            )
            self.assertEqual(len(articles), 1)
            self.assertEqual(articles[0].section, "Belgium")

    def test_attach_swallows_errors(self) -> None:
        existing = [object()]
        with patch(
            "belgium.epub.collect_belgium_epub_articles",
            side_effect=RuntimeError("openai down"),
        ):
            out = try_attach_belgium_articles(existing, enabled=True)
        self.assertIs(out, existing)
        self.assertEqual(len(out), 1)

    def test_stale_run_starts_new_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stale = Path(tmp) / "2026-01-01"
            stale.mkdir()
            (stale / "run.json").write_text(
                json.dumps({"created_at": "2026-01-01T00:00:00Z"}),
                encoding="utf-8",
            )
            self.assertFalse(run_is_fresh(stale))
            created = []

            def fake_pipeline(**kwargs):
                created.append(True)
                fresh = Path(tmp) / "fresh"
                fresh.mkdir()
                (fresh / "articles").mkdir()
                _piece("new").save(fresh / "articles" / "new.json")
                return fresh

            with patch("belgium.epub.latest_run_dir", return_value=stale):
                with patch("belgium.epub.OPENROUTER_API_KEY", "sk-test"):
                    with patch("belgium.epub.run_pipeline", side_effect=fake_pipeline):
                        articles = collect_belgium_epub_articles(generate=True)
            self.assertTrue(created)
            self.assertEqual(articles[0].title, "Belgium's grid <test>")

    def test_saturday_run_is_stale_next_thursday(self) -> None:
        """Last week's Saturday retry must not be reused on this Thursday."""
        with tempfile.TemporaryDirectory() as tmp:
            prior = Path(tmp) / "2026-09-20"
            prior.mkdir()
            (prior / "run.json").write_text(
                json.dumps({"created_at": "2026-09-20T07:23:00Z"}),
                encoding="utf-8",
            )
            thursday_job = datetime(2026, 9, 24, 20, 0, tzinfo=timezone.utc)
            self.assertEqual(
                briefing_window_start(thursday_job),
                datetime(2026, 9, 24, tzinfo=timezone.utc),
            )
            self.assertFalse(run_is_fresh(prior, now=thursday_job))

    def test_thursday_run_is_fresh_on_saturday_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            current = Path(tmp) / "2026-09-24"
            current.mkdir()
            (current / "run.json").write_text(
                json.dumps({"created_at": "2026-09-24T20:22:00Z"}),
                encoding="utf-8",
            )
            saturday = datetime(2026, 9, 26, 9, 0, tzinfo=timezone.utc)
            self.assertTrue(run_is_fresh(current, now=saturday))

    def test_attach_disabled(self) -> None:
        existing = []
        with patch("belgium.epub.collect_belgium_epub_articles") as collect:
            out = try_attach_belgium_articles(existing, enabled=False)
        collect.assert_not_called()
        self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main()
