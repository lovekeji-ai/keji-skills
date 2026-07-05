from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DATE = "2026-06-15"


class AIHotIntegrationFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cache_dir = self.root / "cache"
        self.output_dir = self.root / "output"
        self.daily_cache = self.cache_dir / DATE
        self.daily_cache.mkdir(parents=True)
        self.output_dir.mkdir()
        self.config = self.root / "config.yaml"
        self.config.write_text(
            "\n".join([
                "paths:",
                f"  output_dir: {self.output_dir}",
                f"  cache_dir: {self.cache_dir}",
                "settings:",
                "  default_date: today",
                "  timezone: Asia/Shanghai",
                "pipeline:",
                "  enabled_sources:",
                "    - aihot",
                "  skip_unavailable_sources: true",
                "",
            ]),
            encoding="utf-8",
        )
        self.raw_payload = {
            "source": "aihot",
            "target_date": DATE,
            "timezone": "Asia/Shanghai",
            "request": {"mode": "selected", "since": "2026-06-14T16:00:00Z", "take": 20},
            "response": {"page_count": 1, "truncated": False},
            "items": [
                {
                    "id": "cmqegnuc40214slunxe96pbiy",
                    "title": "OpenAI 推出合作伙伴网络",
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

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_json(self, *args: str) -> dict:
        result = subprocess.run(
            [sys.executable, *args],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

    def test_check_run_state_tracks_aihot_raw_and_normalized_cache(self) -> None:
        (self.daily_cache / "aihot.json").write_text(json.dumps(self.raw_payload), encoding="utf-8")

        raw_state = self.run_json("scripts/check-run-state.py", "--date", DATE, "--config", str(self.config))
        self.assertEqual(raw_state["source_states"]["aihot"]["status"], "raw_only")
        self.assertIn("aihot 只有 raw cache，尚未完成 normalization", raw_state["partial_reasons"])

        subprocess.run(
            [
                sys.executable,
                "scripts/normalize-external-source.py",
                "--source",
                "aihot",
                "--input",
                str(self.daily_cache / "aihot.json"),
                "--output",
                str(self.daily_cache / "aihot-normalized.json"),
            ],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        (self.output_dir / f"{DATE}.md").write_text("# raw\n", encoding="utf-8")
        (self.output_dir / f"{DATE} 摘要.md").write_text("# summary\n", encoding="utf-8")

        complete_state = self.run_json("scripts/check-run-state.py", "--date", DATE, "--config", str(self.config))
        self.assertEqual(complete_state["source_states"]["aihot"]["status"], "complete")
        self.assertFalse(complete_state["is_partial_run"])

    def test_build_summary_context_includes_aihot_items(self) -> None:
        raw_path = self.daily_cache / "aihot.json"
        normalized_path = self.daily_cache / "aihot-normalized.json"
        raw_path.write_text(json.dumps(self.raw_payload), encoding="utf-8")
        subprocess.run(
            [
                sys.executable,
                "scripts/normalize-external-source.py",
                "--source",
                "aihot",
                "--input",
                str(raw_path),
                "--output",
                str(normalized_path),
            ],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        output_path = self.daily_cache / "summary-context.md"
        subprocess.run(
            [
                sys.executable,
                "scripts/build-summary-context.py",
                "--date",
                DATE,
                "--config",
                str(self.config),
                "--output",
                str(output_path),
            ],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        text = output_path.read_text(encoding="utf-8")
        self.assertIn("### aihot", text)
        self.assertIn("aihot_item", text)
        self.assertIn("OpenAI 推出合作伙伴网络", text)


if __name__ == "__main__":
    unittest.main()
