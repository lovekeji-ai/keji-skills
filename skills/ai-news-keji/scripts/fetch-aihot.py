#!/usr/bin/env python3
"""
Fetch AI HOT selected/all items through the public REST API.

The API is anonymous, but /api/public/* rejects default curl-like user agents.
This script bakes in a browser-style UA so cron and Agent runs do not have to
remember that detail.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


DEFAULT_BASE_URL = "https://aihot.virxact.com"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36 ai-news-keji/aihot-fetch/0.1"
)
CATEGORY_CHOICES = ("ai-models", "ai-products", "industry", "paper", "tip")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_timezone(name: str):
    try:
        return ZoneInfo(name)
    except Exception:
        return timezone(timedelta(hours=8))


def parse_target_date(raw_date: str | None, tz) -> str:
    if raw_date:
        return datetime.strptime(raw_date, "%Y-%m-%d").date().isoformat()
    return datetime.now(tz=tz).date().isoformat()


def parse_api_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def day_start_utc(date_text: str, tz) -> datetime:
    local_start = datetime.strptime(date_text, "%Y-%m-%d").replace(tzinfo=tz)
    return local_start.astimezone(timezone.utc)


def same_local_date(value: Any, target_date: str, tz) -> bool:
    parsed = parse_api_datetime(value)
    if not parsed:
        return True
    return parsed.astimezone(tz).date().isoformat() == target_date


def build_items_url(
    *,
    base_url: str,
    mode: str,
    since: str,
    take: int,
    category: str | None,
    query: str | None,
    cursor: str | None = None,
) -> str:
    params: dict[str, str | int] = {
        "mode": mode,
        "since": since,
        "take": take,
    }
    if category:
        params["category"] = category
    if query:
        params["q"] = query
    if cursor:
        params["cursor"] = cursor
    return f"{base_url.rstrip('/')}/api/public/items?{urllib.parse.urlencode(params)}"


def fetch_json(url: str, *, user_agent: str, timeout: int, retries: int) -> tuple[dict[str, Any], dict[str, Any]]:
    last_error: dict[str, Any] | None = None
    for attempt in range(retries + 1):
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": user_agent,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
                payload = json.loads(body)
                if not isinstance(payload, dict):
                    raise ValueError("AI HOT response is not a JSON object")
                meta = {
                    "status": response.status,
                    "etag": response.headers.get("ETag"),
                    "cache_control": response.headers.get("Cache-Control"),
                    "attempts": attempt + 1,
                }
                return payload, meta
        except urllib.error.HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            last_error = {"status": exc.code, "message": message.strip(), "url": url}
            if exc.code not in {429, 503} or attempt >= retries:
                break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            last_error = {"status": "request_error", "message": str(exc), "url": url}
            if attempt >= retries:
                break
        time.sleep(min(2 ** attempt, 4))

    raise RuntimeError(json.dumps(last_error or {"status": "unknown_error", "url": url}, ensure_ascii=False))


def filter_items_for_date(items: list[Any], target_date: str, tz) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            dropped.append({"index": idx, "reason": "item_not_object"})
            continue
        if not item.get("publishedAt"):
            dropped.append({
                "index": idx,
                "reason": "missing_published_at",
                "id": item.get("id"),
                "title": item.get("title"),
            })
            continue
        if parse_api_datetime(item.get("publishedAt")) is None:
            dropped.append({
                "index": idx,
                "reason": "invalid_published_at",
                "id": item.get("id"),
                "publishedAt": item.get("publishedAt"),
                "title": item.get("title"),
            })
            continue
        if same_local_date(item.get("publishedAt"), target_date, tz):
            kept.append(item)
            continue
        dropped.append({
            "index": idx,
            "reason": "outside_target_date",
            "id": item.get("id"),
            "publishedAt": item.get("publishedAt"),
            "title": item.get("title"),
        })
    return kept, dropped


def fetch_item_pages(
    *,
    base_url: str,
    mode: str,
    since: str,
    take: int,
    category: str | None,
    query: str | None,
    user_agent: str,
    timeout: int,
    retries: int,
    max_pages: int,
    page_delay: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    cursor: str | None = None

    for page_index in range(max(max_pages, 1)):
        url = build_items_url(
            base_url=base_url,
            mode=mode,
            since=since,
            take=take,
            category=category,
            query=query,
            cursor=cursor,
        )
        payload, response_meta = fetch_json(
            url,
            user_agent=user_agent,
            timeout=max(timeout, 1),
            retries=max(retries, 0),
        )
        page_items = payload.get("items") if isinstance(payload.get("items"), list) else []
        items.extend(item for item in page_items if isinstance(item, dict))
        cursor = payload.get("nextCursor") if isinstance(payload.get("nextCursor"), str) else None
        has_next = bool(payload.get("hasNext") and cursor)
        pages.append({
            "page": page_index + 1,
            "count": payload.get("count"),
            "item_count": len(page_items),
            "hasNext": payload.get("hasNext"),
            "nextCursor": cursor,
            **response_meta,
        })
        if not has_next:
            break
        if page_delay > 0:
            time.sleep(page_delay)

    return items, pages


def dump_json(payload: dict[str, Any], output: Path | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if output is None:
        print(text)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch AI HOT public items into a raw cache JSON")
    parser.add_argument("--date", default=None, help="Target local date YYYY-MM-DD; defaults to today in --timezone")
    parser.add_argument("--timezone", default="Asia/Shanghai", help="Timezone used for date filtering")
    parser.add_argument("--mode", choices=("selected", "all"), default="selected")
    parser.add_argument("--category", choices=CATEGORY_CHOICES, default=None)
    parser.add_argument("--q", default=None, help="Server-side keyword search")
    parser.add_argument("--take", type=int, default=100, help="Items per request, 1-100")
    parser.add_argument("--since", default=None, help="Override since ISO datetime; defaults to target day start")
    parser.add_argument("--no-date-filter", action="store_true", help="Keep all returned items instead of filtering to --date")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--max-pages", type=int, default=5, help="Max cursor pages to fetch")
    parser.add_argument("--page-delay", type=float, default=0.2, help="Delay between cursor pages")
    parser.add_argument("--output", default=None, help="Write JSON here instead of stdout")
    args = parser.parse_args()

    if not 1 <= args.take <= 100:
        raise SystemExit("--take must be between 1 and 100")

    tz = load_timezone(args.timezone)
    target_date = parse_target_date(args.date, tz)
    since_dt = day_start_utc(target_date, tz)
    since = args.since or since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    raw_items, pages = fetch_item_pages(
        base_url=args.base_url,
        mode=args.mode,
        since=since,
        take=args.take,
        category=args.category,
        query=args.q,
        user_agent=args.user_agent,
        timeout=args.timeout,
        retries=args.retries,
        max_pages=args.max_pages,
        page_delay=args.page_delay,
    )
    if args.no_date_filter:
        items = raw_items
        dropped: list[dict[str, Any]] = []
    else:
        items, dropped = filter_items_for_date(raw_items, target_date, tz)

    output = {
        "schema_version": 1,
        "source": "aihot",
        "fetched_at": now_iso(),
        "target_date": target_date,
        "timezone": args.timezone,
        "base_url": args.base_url.rstrip("/"),
        "request": {
            "endpoint": "/api/public/items",
            "mode": args.mode,
            "category": args.category,
            "q": args.q,
            "since": since,
            "take": args.take,
            "date_filter_enabled": not args.no_date_filter,
        },
        "response": {
            "pages": pages,
            "page_count": len(pages),
            "truncated": bool(pages and pages[-1].get("hasNext") and pages[-1].get("nextCursor")),
            "last_nextCursor": pages[-1].get("nextCursor") if pages else None,
        },
        "items": items,
        "dropped": dropped,
        "stats": {
            "raw_items": len(raw_items),
            "kept_items": len(items),
            "dropped_items": len(dropped),
        },
    }
    output_path = Path(args.output).expanduser().resolve() if args.output else None
    dump_json(output, output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
