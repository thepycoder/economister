"""Tests for the Belgium pipeline stage machine (mocked agents)."""

from __future__ import annotations

import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from unittest.mock import MagicMock

from belgium.models import SourceArticle, SourceIndex
from belgium.pipeline import (
    PipelineError,
    resolve_stages,
    run_pipeline,
    stage_curate,
    stage_ingest,
    stage_write,
)
from belgium.vrt_client import write_source_pack


def _long_paragraphs(n: int = 6) -> list:
    sentence = (
        "Belgium remains an awkward middle power in European politics, "
        "balancing Flemish and Walloon interests while hosting EU institutions "
        "that increasingly set the agenda for energy and fiscal policy. "
    )
    return [sentence * 2 for _ in range(n)]


class TestPipelineMocked(unittest.TestCase):
    """End-to-end pipeline with mocked VRT and Claude."""

    def _seed_sources(self, run_dir: Path) -> None:
        index = SourceIndex(
            fetched_at="2026-09-19T12:00:00Z",
            days=7,
            articles=[
                SourceArticle(
                    title="Belgium debates nuclear extension",
                    url="https://www.vrt.be/vrtnws/nl/2026/09/18/nuclear/",
                    published="2026-09-18T10:00:00Z",
                    category="Binnenland",
                    summary="Government talks continue.",
                    body="Detailed Dutch body about nuclear policy.",
                    slug="nuclear",
                ),
                SourceArticle(
                    title="Port of Antwerp traffic rises",
                    url="https://www.vrt.be/vrtnws/nl/2026/09/17/antwerp/",
                    published="2026-09-17T10:00:00Z",
                    category="Binnenland",
                    summary="Containers up.",
                    body="Detailed Dutch body about the port.",
                    slug="antwerp",
                ),
            ],
        )
        write_source_pack(index, run_dir)

    def test_curate_and_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            self._seed_sources(run_dir)

            def fake_curator(**kwargs):
                return {
                    "topics": [
                        {
                            "slug": "nuclear-extension",
                            "working_hed": "Belgium's nuclear extension",
                            "why_economist": "Energy security with EU stakes.",
                            "source_urls": [
                                "https://www.vrt.be/vrtnws/nl/2026/09/18/nuclear/"
                            ],
                            "confidence": 0.9,
                        }
                    ]
                }, "gen-curate"

            def fake_writer(**kwargs):
                return {
                    "articles": [
                        {
                            "title": "Belgium's nuclear gamble",
                            "subtitle": "Reactors, politics and the grid",
                            "slug": "nuclear-extension",
                            "section": "Belgium",
                            "paragraphs": _long_paragraphs(),
                            "sources": [
                                {
                                    "title": "VRT nuclear",
                                    "url": "https://www.vrt.be/vrtnws/nl/2026/09/18/nuclear/",
                                    "publisher": "VRT NWS",
                                },
                                {
                                    "title": "Extra briefing",
                                    "url": "https://example.com/briefing",
                                    "publisher": "Example",
                                },
                            ],
                            "topic_rationale": "Energy policy with EU stakes.",
                        }
                    ]
                }, "gen-write"

            shortlist = stage_curate(
                run_dir, max_topics=3, curator_fn=fake_curator
            )
            self.assertEqual(len(shortlist.topics), 1)
            self.assertTrue((run_dir / "shortlist.json").exists())

            articles = stage_write(run_dir, writer_fn=fake_writer)
            self.assertEqual(len(articles), 1)
            out = run_dir / "articles" / "nuclear-extension.json"
            self.assertTrue(out.exists())
            md = run_dir / "articles" / "nuclear-extension.md"
            self.assertTrue(md.exists())
            self.assertIn("# Belgium's nuclear gamble", md.read_text(encoding="utf-8"))
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["section"], "Belgium")
            self.assertEqual(len(payload["sources"]), 2)

            run_state = json.loads(
                (run_dir / "run.json").read_text(encoding="utf-8")
            )
            self.assertEqual(run_state["stages"]["curate"]["status"], "ok")
            self.assertEqual(run_state["stages"]["write"]["status"], "ok")

    def test_curate_skips_existing_slug(self) -> None:
        from belgium.models import BelgiumArticle
        from belgium.pipeline import filter_duplicate_topics
        from belgium.models import Shortlist, TopicCandidate

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            self._seed_sources(run_dir)
            existing = BelgiumArticle(
                title="Belgium's nuclear gamble",
                slug="nuclear-extension",
                paragraphs=_long_paragraphs(),
                sources=[{
                    "title": "VRT",
                    "url": "https://www.vrt.be/vrtnws/nl/2026/09/18/nuclear/",
                }],
                topic_rationale="Already done.",
            )
            # ArticleSource expects objects via from_dict path - use from_dict
            existing = BelgiumArticle.from_dict({
                "title": "Belgium's nuclear gamble",
                "slug": "nuclear-extension",
                "section": "Belgium",
                "paragraphs": _long_paragraphs(),
                "sources": [{
                    "title": "VRT",
                    "url": "https://www.vrt.be/vrtnws/nl/2026/09/18/nuclear/",
                }],
                "topic_rationale": "Already done.",
            })
            (run_dir / "articles").mkdir(parents=True)
            existing.save(run_dir / "articles" / "nuclear-extension.json")

            seen: dict = {}

            def fake_curator(**kwargs):
                seen["excluded"] = kwargs.get("excluded_topics")
                return {
                    "topics": [
                        {
                            "slug": "nuclear-extension",
                            "working_hed": "Dup",
                            "why_economist": "Dup why.",
                            "source_urls": [
                                "https://www.vrt.be/vrtnws/nl/2026/09/18/nuclear/"
                            ],
                            "confidence": 0.9,
                        },
                        {
                            "slug": "port-antwerp",
                            "working_hed": "Antwerp",
                            "why_economist": "Trade.",
                            "source_urls": [
                                "https://www.vrt.be/vrtnws/nl/2026/09/17/antwerp/"
                            ],
                            "confidence": 0.8,
                        },
                    ]
                }, "gen"

            shortlist = stage_curate(run_dir, max_topics=2, curator_fn=fake_curator)
            self.assertIn("nuclear-extension", seen["excluded"] or "")
            self.assertEqual([t.slug for t in shortlist.topics], ["port-antwerp"])

            # Write should refuse if shortlist only has existing slug
            shortlist_all = Shortlist(topics=[
                TopicCandidate(
                    slug="nuclear-extension",
                    working_hed="Dup",
                    why_economist="Dup why.",
                    source_urls=["https://www.vrt.be/vrtnws/nl/2026/09/18/nuclear/"],
                    confidence=0.9,
                )
            ])
            shortlist_all.save(run_dir / "shortlist.json")
            with self.assertRaises(PipelineError):
                stage_write(run_dir, writer_fn=lambda **k: ({"articles": []}, "x"))

            filtered = filter_duplicate_topics(
                Shortlist(topics=shortlist_all.topics + [
                    TopicCandidate(
                        slug="port-antwerp",
                        working_hed="Antwerp",
                        why_economist="Trade.",
                        source_urls=["https://www.vrt.be/vrtnws/nl/2026/09/17/antwerp/"],
                        confidence=0.8,
                    )
                ]),
                excluded_slugs={"nuclear-extension"},
            )
            self.assertEqual([t.slug for t in filtered.topics], ["port-antwerp"])

    def test_from_stage_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            self._seed_sources(run_dir)
            (run_dir / "shortlist.json").write_text(
                json.dumps({
                    "topics": [
                        {
                            "slug": "port-antwerp",
                            "working_hed": "Antwerp's container boom",
                            "why_economist": "Trade and chemicals.",
                            "source_urls": [
                                "https://www.vrt.be/vrtnws/nl/2026/09/17/antwerp/"
                            ],
                            "confidence": 0.7,
                        }
                    ]
                }),
                encoding="utf-8",
            )

            def fake_writer(**kwargs):
                return {
                    "articles": [
                        {
                            "title": "Antwerp's container boom",
                            "subtitle": "Europe's gateway",
                            "slug": "port-antwerp",
                            "section": "Belgium",
                            "paragraphs": _long_paragraphs(),
                            "sources": [
                                {
                                    "title": "VRT",
                                    "url": "https://www.vrt.be/vrtnws/nl/2026/09/17/antwerp/",
                                }
                            ],
                            "topic_rationale": "Trade.",
                        }
                    ]
                }, "gen"

            path = run_pipeline(
                run_dir=run_dir,
                from_stage="write",
                writer_fn=fake_writer,
            )
            self.assertEqual(path, run_dir)
            self.assertTrue((run_dir / "articles" / "port-antwerp.json").exists())

    def test_write_isolates_each_topic(self) -> None:
        """Each shortlist topic gets its own writer call and shortlist JSON."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            self._seed_sources(run_dir)
            (run_dir / "shortlist.json").write_text(
                json.dumps({
                    "topics": [
                        {
                            "slug": "nuclear-extension",
                            "working_hed": "Belgium's nuclear extension",
                            "why_economist": "Energy security with EU stakes.",
                            "source_urls": [
                                "https://www.vrt.be/vrtnws/nl/2026/09/18/nuclear/"
                            ],
                            "confidence": 0.9,
                        },
                        {
                            "slug": "port-antwerp",
                            "working_hed": "Antwerp's container boom",
                            "why_economist": "Trade and chemicals.",
                            "source_urls": [
                                "https://www.vrt.be/vrtnws/nl/2026/09/17/antwerp/"
                            ],
                            "confidence": 0.7,
                        },
                    ]
                }),
                encoding="utf-8",
            )

            calls: list[dict] = []

            def fake_writer(**kwargs):
                payload = json.loads(kwargs["shortlist_json"])
                calls.append(payload)
                slug = payload["topics"][0]["slug"]
                return {
                    "articles": [
                        {
                            "title": f"Title for {slug}",
                            "subtitle": "Dek",
                            "slug": slug,
                            "section": "Belgium",
                            "paragraphs": _long_paragraphs(),
                            "sources": [
                                {
                                    "title": "VRT",
                                    "url": payload["topics"][0]["source_urls"][0],
                                }
                            ],
                            "topic_rationale": "Isolated write.",
                        }
                    ]
                }, {
                    "generation_id": f"gen-{slug}",
                    "cost_usd": 0.1,
                    "effective_cost_usd": 0.1,
                    "tokens_prompt": 10,
                    "tokens_completion": 20,
                }

            articles = stage_write(run_dir, writer_fn=fake_writer)
            self.assertEqual(len(articles), 2)
            self.assertEqual(len(calls), 2)
            self.assertEqual([c["topics"][0]["slug"] for c in calls], [
                "nuclear-extension",
                "port-antwerp",
            ])
            for call in calls:
                self.assertEqual(len(call["topics"]), 1)
            self.assertTrue((run_dir / "articles" / "nuclear-extension.json").exists())
            self.assertTrue((run_dir / "articles" / "port-antwerp.json").exists())

            run_state = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            write_usage = run_state["stages"]["write"]["usage"]
            self.assertAlmostEqual(write_usage["effective_cost_usd"], 0.2)
            self.assertEqual(len(write_usage["articles"]), 2)

    def test_ingest_stage_mocked(self) -> None:
        client = MagicMock()
        from belgium.models import SourceIndex as SI

        fake_index = SI(
            fetched_at="2026-09-19T12:00:00Z",
            days=7,
            articles=[
                SourceArticle(
                    title="T",
                    url="https://www.vrt.be/vrtnws/nl/x/",
                    body="Body",
                    slug="x",
                )
            ],
        )

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            with unittest.mock.patch(
                "belgium.pipeline.collect_week", return_value=fake_index
            ):
                index = stage_ingest(run_dir, days=7, client=client)
            self.assertEqual(len(index.articles), 1)
            self.assertTrue((run_dir / "sources" / "index.json").exists())

    def test_curate_requires_ingest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(PipelineError):
                stage_curate(Path(tmp), curator_fn=lambda **k: ({}, None))

    def test_resolve_stages_to_curate(self) -> None:
        self.assertEqual(list(resolve_stages(to_stage="curate")), ["ingest", "curate"])
        self.assertEqual(list(resolve_stages(from_stage="write")), ["write"])
        with self.assertRaises(PipelineError):
            resolve_stages(stage="ingest", to_stage="curate")


if __name__ == "__main__":
    unittest.main()
