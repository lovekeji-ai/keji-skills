from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fetch-aihot.py"
SPEC = importlib.util.spec_from_file_location("fetch_aihot", MODULE_PATH)
assert SPEC and SPEC.loader
fetch_aihot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fetch_aihot)


class FakeResponse:
    status = 200
    headers = {"ETag": 'W/"items-test"', "Cache-Control": "public, s-maxage=300"}

    def __init__(self, payload=None):
        self.payload = payload or {"items": [], "count": 0, "hasNext": False}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class FetchAIHotTests(unittest.TestCase):
    def test_fetch_json_sends_required_user_agent(self) -> None:
        seen = {}

        def fake_urlopen(request, timeout):
            seen["user_agent"] = request.get_header("User-agent")
            seen["accept"] = request.get_header("Accept")
            seen["timeout"] = timeout
            return FakeResponse()

        with mock.patch.object(fetch_aihot.urllib.request, "urlopen", side_effect=fake_urlopen):
            payload, meta = fetch_aihot.fetch_json(
                "https://aihot.virxact.com/api/public/items?mode=selected&take=1",
                user_agent="Browser UA ai-news-keji/aihot-fetch-test",
                timeout=7,
                retries=0,
            )

        self.assertEqual(payload["count"], 0)
        self.assertEqual(meta["status"], 200)
        self.assertIn("aihot-fetch-test", seen["user_agent"])
        self.assertEqual(seen["accept"], "application/json")
        self.assertEqual(seen["timeout"], 7)

    def test_filter_items_for_target_date_in_timezone(self) -> None:
        tz = ZoneInfo("Asia/Shanghai")
        kept, dropped = fetch_aihot.filter_items_for_date(
            [
                {"id": "same", "publishedAt": "2026-06-14T17:00:00.000Z", "title": "local 6/15"},
                {"id": "outside", "publishedAt": "2026-06-13T17:00:00.000Z", "title": "local 6/14"},
                {"id": "missing-date", "title": "drop missing date"},
                {"id": "bad-date", "publishedAt": "not a date", "title": "drop bad date"},
            ],
            "2026-06-15",
            tz,
        )

        self.assertEqual([item["id"] for item in kept], ["same"])
        self.assertEqual([item["reason"] for item in dropped], [
            "outside_target_date",
            "missing_published_at",
            "invalid_published_at",
        ])

    def test_fetch_item_pages_follows_next_cursor(self) -> None:
        urls = []
        responses = [
            FakeResponse({
                "items": [{"id": "first"}],
                "count": 1,
                "hasNext": True,
                "nextCursor": "cursor-2",
            }),
            FakeResponse({
                "items": [{"id": "second"}],
                "count": 1,
                "hasNext": False,
                "nextCursor": None,
            }),
        ]

        def fake_urlopen(request, timeout):
            urls.append(request.full_url)
            return responses.pop(0)

        with mock.patch.object(fetch_aihot.urllib.request, "urlopen", side_effect=fake_urlopen):
            items, pages = fetch_aihot.fetch_item_pages(
                base_url="https://aihot.virxact.com",
                mode="selected",
                since="2026-06-14T16:00:00Z",
                take=1,
                category=None,
                query=None,
                user_agent="Browser UA ai-news-keji/aihot-fetch-test",
                timeout=7,
                retries=0,
                max_pages=5,
                page_delay=0,
            )

        self.assertEqual([item["id"] for item in items], ["first", "second"])
        self.assertEqual(len(pages), 2)
        self.assertNotIn("cursor=", urls[0])
        self.assertIn("cursor=cursor-2", urls[1])


if __name__ == "__main__":
    unittest.main()
