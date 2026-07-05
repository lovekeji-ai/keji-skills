#!/usr/bin/env python3
"""
分析 ai-news-keji 某日缓存的新鲜度，区分“当天/近 7 天的硬新闻”与“较新的深读来源”。

用途：在写摘要前，先判断当天到底是“新闻少但有新深读”，还是“各来源整体都旧”。
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from _runtime import ensure_modules

ensure_modules(["yaml"])

import yaml

SKILL_ROOT = Path(__file__).resolve().parent.parent


def expand_path(value: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(value))).resolve()


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_json_if_exists(path: Path) -> Any | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def load_timezone(name: str):
    try:
        return ZoneInfo(name)
    except Exception:
        return timezone(timedelta(hours=8))


def resolve_target_date(raw_date: str | None, config: dict) -> str:
    settings = config.get("settings") or {}
    tz = load_timezone(str(settings.get("timezone") or "Asia/Shanghai"))
    if raw_date:
        return datetime.strptime(raw_date, "%Y-%m-%d").date().isoformat()
    default_date = str(settings.get("default_date") or "yesterday")
    now = datetime.now(tz=tz)
    if default_date == "today":
        return now.date().isoformat()
    return (now - timedelta(days=1)).date().isoformat()


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    for fmt in (
        None,
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S +0000 (UTC)",
    ):
        try:
            if fmt is None:
                parsed = datetime.fromisoformat(text)
            else:
                parsed = datetime.strptime(text, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
    return None


def age_bucket(parsed: datetime | None, target_date: str) -> str:
    if parsed is None:
        return "undated"
    target = datetime.strptime(target_date, "%Y-%m-%d").date()
    delta = (target - parsed.date()).days
    if delta < 0:
        return "future"
    if delta <= 1:
        return "fresh_48h"
    if delta <= 7:
        return "recent_7d"
    return "stale_gt7d"


def normalize_items(source: str, payload: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if source == "rss" and isinstance(payload, dict):
        for feed in payload.get("feeds") or []:
            for entry in feed.get("entries") or []:
                items.append({
                    "title": entry.get("title"),
                    "published_at": entry.get("published") or entry.get("published_at"),
                    "url": entry.get("link"),
                })
    elif source == "email" and isinstance(payload, dict):
        for entry in payload.get("entries") or []:
            items.append({
                "title": entry.get("title") or entry.get("subject"),
                "published_at": entry.get("date") or entry.get("published_at"),
                "url": entry.get("link") or entry.get("url"),
            })
    elif isinstance(payload, dict):
        for entry in payload.get("items") or []:
            if not isinstance(entry, dict):
                continue
            deep_read = entry["deep_read"] if isinstance(entry.get("deep_read"), dict) else {}
            items.append({
                "title": entry.get("title"),
                "published_at": entry.get("published_at") or entry.get("published_local") or deep_read.get("publish_datetime"),
                "url": entry.get("url"),
            })
    return items


def summarize_source(source: str, items: list[dict[str, Any]], target_date: str) -> dict[str, Any]:
    counter = Counter()
    samples: list[dict[str, Any]] = []
    for item in items:
        parsed = parse_datetime(item.get("published_at"))
        bucket = age_bucket(parsed, target_date)
        counter[bucket] += 1
        if len(samples) < 3:
            samples.append({
                "title": item.get("title"),
                "published_at": item.get("published_at"),
                "bucket": bucket,
            })
    return {
        "source": source,
        "total": len(items),
        "fresh_48h": counter["fresh_48h"],
        "recent_7d": counter["recent_7d"],
        "stale_gt7d": counter["stale_gt7d"],
        "undated": counter["undated"],
        "future": counter["future"],
        "samples": samples,
    }


def overall_conclusion(summaries: list[dict[str, Any]]) -> list[str]:
    by_source = {item["source"]: item for item in summaries}
    hard_sources = ("rss", "email", "aihot")
    deep_sources = ("bestblogs", "follow-builders", "ak-rss-digest")
    hard_fresh = sum(by_source.get(name, {}).get("fresh_48h", 0) for name in hard_sources)
    hard_recent = sum(by_source.get(name, {}).get("recent_7d", 0) for name in hard_sources)
    deep_fresh = sum(by_source.get(name, {}).get("fresh_48h", 0) for name in deep_sources)
    deep_recent = sum(by_source.get(name, {}).get("recent_7d", 0) for name in deep_sources)

    conclusions: list[str] = []
    if hard_fresh == 0 and hard_recent == 0:
        conclusions.append("硬新闻来源（rss/email/aihot）没有最近 7 天的新内容。今天不应强写主线新闻，应转为“无明显新硬新闻 + 深读分析/趋势判断”。")
    elif hard_fresh == 0:
        conclusions.append("硬新闻来源没有 48 小时内的新内容；如果继续写日报，必须把内容表述为最近几天的延续，而不是今天新发布。")
    if deep_fresh + deep_recent > 0 and hard_fresh == 0:
        conclusions.append("深读来源（如 BestBlogs）比硬新闻来源更新，版面应允许新深读上浮，或明确说明“今天主线新闻偏少，本期以高价值深读为主”。")
    if not conclusions:
        conclusions.append("硬新闻来源与深读来源都存在较新的内容，可以正常进入写稿阶段，但仍需做跨天去重。")
    return conclusions


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze source freshness for ai-news-keji caches")
    parser.add_argument("--date", default=None, help="Target date YYYY-MM-DD")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    args = parser.parse_args()

    config_path = Path(args.config).expanduser()
    if not config_path.is_absolute():
        config_path = SKILL_ROOT / config_path
    config = load_yaml(config_path)
    target_date = resolve_target_date(args.date, config)
    paths = config.get("paths") or {}
    cache_root = expand_path(str(paths.get("cache_dir") or "~/.cache/ai-news-keji"))
    cache_dir = cache_root / target_date

    payloads = {
        "rss": load_json_if_exists(cache_dir / "rss-raw.json"),
        "email": load_json_if_exists(cache_dir / "email-raw.json"),
        "aihot": load_json_if_exists(cache_dir / "aihot-normalized.json"),
        "bestblogs": load_json_if_exists(cache_dir / "bestblogs-normalized.json"),
        "follow-builders": load_json_if_exists(cache_dir / "follow-builders-normalized.json"),
        "ak-rss-digest": load_json_if_exists(cache_dir / "ak-rss-digest-normalized.json"),
    }

    summaries = [
        summarize_source(source, normalize_items(source, payload), target_date)
        for source, payload in payloads.items()
    ]

    print(json.dumps({
        "date": target_date,
        "cache_dir": str(cache_dir),
        "source_summaries": summaries,
        "conclusions": overall_conclusion(summaries),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
