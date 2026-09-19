"""Tests for OpenRouter agent helpers (no network)."""

from __future__ import annotations

import unittest

from belgium.agents import AgentError, extract_json_object, load_prompt, normalize_writer_payload


class TestExtractJson(unittest.TestCase):
    """JSON extraction from model text."""

    def test_plain_object(self) -> None:
        data = extract_json_object('{"topics": []}')
        self.assertEqual(data["topics"], [])

    def test_fenced(self) -> None:
        text = 'Here you go:\n```json\n{"a": 1}\n```\n'
        self.assertEqual(extract_json_object(text), {"a": 1})

    def test_invalid(self) -> None:
        with self.assertRaises(AgentError):
            extract_json_object("not json at all")


class TestNormalizeWriter(unittest.TestCase):
    """Writer payload shapes."""

    def test_articles_array(self) -> None:
        items = normalize_writer_payload({
            "articles": [{"title": "A", "paragraphs": ["x"]}]
        })
        self.assertEqual(len(items), 1)

    def test_single_article(self) -> None:
        items = normalize_writer_payload({
            "title": "A",
            "paragraphs": ["x"],
        })
        self.assertEqual(items[0]["title"], "A")

    def test_bad_shape(self) -> None:
        with self.assertRaises(AgentError):
            normalize_writer_payload({"foo": 1})


class TestLoadPrompt(unittest.TestCase):
    """Prompt file loading."""

    def test_curator_placeholder(self) -> None:
        text = load_prompt(
            "curator.md",
            MAX_TOPICS=3,
            EXCLUDED_TOPICS="- `old-slug`: Old title",
        )
        self.assertIn("1 to 3", text)
        self.assertNotIn("{{MAX_TOPICS}}", text)
        self.assertIn("`old-slug`", text)
        self.assertNotIn("{{EXCLUDED_TOPICS}}", text)

    def test_writer_is_single_article(self) -> None:
        text = load_prompt("writer.md")
        self.assertIn("exactly one", text.lower())
        self.assertNotIn("every topic in the shortlist", text)


class TestUsageHelpers(unittest.TestCase):
    """Cost/usage normalization."""

    def test_byok_uses_upstream(self) -> None:
        from belgium.agents import effective_cost_usd, normalize_generation_usage

        usage = normalize_generation_usage({
            "id": "gen-1",
            "total_cost": 0,
            "usage": 0,
            "upstream_inference_cost": 0.12,
            "is_byok": True,
            "native_tokens_prompt": 100,
            "native_tokens_completion": 50,
        })
        self.assertEqual(usage["effective_cost_usd"], 0.12)
        self.assertEqual(effective_cost_usd(usage), 0.12)

    def test_billed_cost_preferred(self) -> None:
        from belgium.agents import effective_cost_usd

        self.assertEqual(
            effective_cost_usd({"cost_usd": 0.05, "upstream_inference_cost_usd": 0.09}),
            0.05,
        )

    def test_unpack_legacy(self) -> None:
        from belgium.agents import unpack_agent_result

        data, usage = unpack_agent_result(({"topics": []}, "gen-abc"))
        self.assertEqual(usage["generation_id"], "gen-abc")
        self.assertEqual(data["topics"], [])


if __name__ == "__main__":
    unittest.main()
