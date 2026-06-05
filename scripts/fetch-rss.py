#!/usr/bin/env python3
"""
RSS 抓取脚本：读取 sources.yaml 中的 RSS 源，获取指定日期的条目。
输出 JSON 到 stdout。
"""
from __future__ import annotations

import argparse
import calendar
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from _runtime import ensure_modules

ensure_modules(["feedparser", "yaml"])

try:
    import feedparser
except ImportError:
    print("错误：未安装 feedparser。请在仓库根目录运行：.venv/bin/python -m pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)

try:
    import yaml
except ImportError:
    print("错误：未安装 PyYAML。请在仓库根目录运行：.venv/bin/python -m pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)


SKILL_ROOT = Path(__file__).resolve().parent.parent


def load_timezone(name: str):
    try:
        return ZoneInfo(name)
    except Exception:
        return timezone(timedelta(hours=8))


def default_sources_path() -> Path:
    local_sources = SKILL_ROOT / "sources.yaml"
    if local_sources.exists():
        return local_sources
    return SKILL_ROOT / "sources.example.yaml"


def parse_date(date_str: str, tz) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=tz)


def is_same_day(entry_date, target_date: datetime, tz) -> bool:
    """Check if an entry was published on the target date (Asia/Shanghai)."""
    if entry_date is None:
        return False

    try:
        ts = calendar.timegm(entry_date)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(tz)
        return dt.date() == target_date.date()
    except Exception:
        return False


def fetch_feed(feed_config: dict, target_date: datetime, tz) -> dict:
    """Fetch a single RSS feed and filter entries by date."""
    name = feed_config["name"]
    url = feed_config["url"]
    category = feed_config.get("category", "")

    try:
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            return {"name": name, "url": url, "error": str(feed.bozo_exception), "entries": []}

        entries = []
        for entry in feed.entries:
            pub_date = entry.get("published_parsed") or entry.get("updated_parsed")

            if not is_same_day(pub_date, target_date, tz):
                continue

            entries.append({
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "summary": (entry.get("summary") or entry.get("description") or "")[:500],
                "published": entry.get("published", ""),
            })

        return {
            "name": name,
            "url": url,
            "category": category,
            "entries": entries,
            "total_in_feed": len(feed.entries),
        }

    except Exception as e:
        return {"name": name, "url": url, "error": str(e), "entries": []}


def main():
    parser = argparse.ArgumentParser(description="Fetch RSS feeds for a given date")
    parser.add_argument("--date", default=None, help="Target date YYYY-MM-DD (default: yesterday)")
    parser.add_argument("--config", default=None,
                        help="Path to sources.yaml (default: sources.yaml, fallback: sources.example.yaml)")
    parser.add_argument("--timezone", default="Asia/Shanghai", help="IANA timezone for date filtering")
    args = parser.parse_args()

    tz = load_timezone(args.timezone)
    if args.date:
        target_date = parse_date(args.date, tz)
    else:
        now = datetime.now(tz=tz)
        target_date = now - timedelta(days=1)

    config_path = Path(args.config).expanduser() if args.config else default_sources_path()
    if not config_path.exists():
        print(f"Error: source config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    rss_sources = config.get("rss", [])
    if not rss_sources:
        print(json.dumps({"date": target_date.strftime("%Y-%m-%d"), "feeds": [], "error": "No RSS sources configured"}))
        sys.exit(0)

    results = []
    for source in rss_sources:
        result = fetch_feed(source, target_date, tz)
        results.append(result)

    output = {
        "date": target_date.strftime("%Y-%m-%d"),
        "feeds": results,
        "stats": {
            "total_feeds": len(results),
            "total_entries": sum(len(r["entries"]) for r in results),
            "feeds_with_entries": sum(1 for r in results if r["entries"]),
            "feeds_with_errors": sum(1 for r in results if "error" in r),
        }
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
