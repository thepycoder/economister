"""Tests for Claude agent helpers (no network)."""

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

    def test_opus_list_price(self) -> None:
        from belgium.agents import estimate_cost_usd

        usage = {
            "input_tokens": 1_000_000,
            "output_tokens": 100_000,
            "cache_read_input_tokens": 1_000_000,
            "server_tool_use": {"web_search_requests": 3},
        }
        # $4 input + $2 output + $0.20 cache read + 3 searches at $0.01.
        self.assertAlmostEqual(estimate_cost_usd("claude-opus-5-5", usage), 6.23)

    def test_unknown_model_unpriced(self) -> None:
        from belgium.agents import estimate_cost_usd

        self.assertIsNone(estimate_cost_usd("claude-unknown", {"input_tokens": 1}))

    def test_paused_turns_summed(self) -> None:
        from types import SimpleNamespace

        from belgium.agents import usage_from_responses

        def response(msg_id: str, searches: int) -> SimpleNamespace:
            return SimpleNamespace(
                id=msg_id,
                model="claude-opus-5-5",
                usage=SimpleNamespace(
                    input_tokens=1000,
                    output_tokens=500,
                    cache_creation_input_tokens=None,
                    cache_read_input_tokens=0,
                    server_tool_use=SimpleNamespace(web_search_requests=searches),
                ),
            )

        usage = usage_from_responses([response("msg_1", 5), response("msg_2", 2)])
        self.assertEqual(usage["generation_id"], "msg_2")
        self.assertEqual(usage["tokens_prompt"], 2000)
        self.assertEqual(usage["tokens_completion"], 1000)
        self.assertEqual(usage["web_search_requests"], 7)
        self.assertAlmostEqual(usage["effective_cost_usd"], 0.008 + 0.02 + 0.07)

    def test_legacy_effective_cost_preferred(self) -> None:
        from belgium.agents import effective_cost_usd

        self.assertEqual(
            effective_cost_usd({"cost_usd": 0.0, "effective_cost_usd": 0.12}),
            0.12,
        )
        self.assertEqual(effective_cost_usd({"cost_usd": 0.05}), 0.05)

    def test_unpack_legacy(self) -> None:
        from belgium.agents import unpack_agent_result

        data, usage = unpack_agent_result(({"topics": []}, "gen-abc"))
        self.assertEqual(usage["generation_id"], "gen-abc")
        self.assertEqual(data["topics"], [])


if __name__ == "__main__":
    unittest.main()
