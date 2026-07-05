from __future__ import annotations

import importlib.util
import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "normalize-external-source.py"
SPEC = importlib.util.spec_from_file_location("normalize_external_source", MODULE_PATH)
assert SPEC and SPEC.loader
normalize_external_source = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(normalize_external_source)


class LoadBestblogsDeepTests(unittest.TestCase):
    def test_prefers_successful_json_even_if_stdout_contains_429_digits(self) -> None:
        payload = {
            "success": True,
            "data": {
                "meta": {
                    "id": "RAW_11f30fed",
                    "title": "Claude Fable 5 与 Claude Mythos 5",
                    "url": "https://www.anthropic.com/news/claude-fable-5-mythos-5",
                    "readUrl": "https://www.bestblogs.dev/article/11f30fed",
                },
                "markdown": (
                    "Using it after that will require "
                    "https://support.claude.com/en/articles/12429409-manage-usage-credits-for-paid-claude-plans"
                ),
            },
        }
        completed = subprocess.CompletedProcess(
            args=["bestblogs", "read", "deep", "RAW_11f30fed", "--json"],
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

        with mock.patch.object(normalize_external_source.subprocess, "run", return_value=completed):
            meta, error = normalize_external_source.load_bestblogs_deep("RAW_11f30fed")

        self.assertIsNone(error)
        self.assertEqual(meta["url"], "https://www.anthropic.com/news/claude-fable-5-mythos-5")
        self.assertEqual(meta["readUrl"], "https://www.bestblogs.dev/article/11f30fed")

    def test_marks_rate_limited_when_output_only_contains_rate_limit_signal(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["bestblogs", "read", "deep", "RAW_x", "--json"],
            returncode=1,
            stdout="",
            stderr="RATE_LIMITED: quota exceeded",
        )

        with mock.patch.object(normalize_external_source.subprocess, "run", return_value=completed):
            meta, error = normalize_external_source.load_bestblogs_deep("RAW_x")

        self.assertIsNone(meta)
        self.assertEqual(error["status"], "rate_limited")


class NormalizeAIHotTests(unittest.TestCase):
    def test_normalizes_aihot_items_into_common_schema(self) -> None:
        payload = {
            "target_date": "2026-06-15",
            "timezone": "Asia/Shanghai",
            "request": {"mode": "selected", "since": "2026-06-14T16:00:00Z"},
            "response": {"count": 1},
            "items": [
                {
                    "id": "cmqegnuc40214slunxe96pbiy",
                    "title": "OpenAI 推出合作伙伴网络",
                    "title_en": "Introducing the OpenAI Partner Network",
                    "url": "https://openai.com/index/introducing-openai-partner-network",
                    "source": "OpenAI：官网动态（RSS）",
                    "publishedAt": "2026-06-14T17:00:00.000Z",
                    "summary": "OpenAI 宣布推出 OpenAI Partner Network。",
                    "category": "industry",
                    "score": 59,
                    "selected": True,
                }
            ],
        }

        normalized = normalize_external_source.normalize_aihot(payload)

        self.assertEqual(normalized["source"], "aihot")
        self.assertEqual(normalized["stats"]["normalized_items"], 1)
        item = normalized["items"][0]
        self.assertEqual(item["kind"], "aihot_item")
        self.assertEqual(item["url"], "https://openai.com/index/introducing-openai-partner-network")
        self.assertEqual(item["source_name"], "OpenAI：官网动态（RSS）")
        self.assertEqual(item["confidence"], "high")
        self.assertTrue(item["has_direct_url"])

    def test_drops_aihot_items_without_direct_url(self) -> None:
        normalized = normalize_external_source.normalize_aihot({
            "items": [{"id": "x", "title": "No URL", "summary": "summary"}],
        })

        self.assertEqual(normalized["items"], [])
        self.assertEqual(normalized["dropped"][0]["reason"], "missing_title_or_url")


if __name__ == "__main__":
    unittest.main()
