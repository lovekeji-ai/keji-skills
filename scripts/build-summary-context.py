#!/usr/bin/env python3
"""
把 ai-news-keji 的缓存产物压缩成给 LLM 使用的小上下文，避免直接读取整份 raw JSON / 原始稿。

默认输出 Markdown，适合直接作为日报原始稿/摘要稿的输入材料。
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from _runtime import ensure_modules

ensure_modules(["yaml"])

import yaml

SKILL_ROOT = Path(__file__).resolve().parent.parent
AI_KEYWORDS = (
    "ai", "llm", "agent", "agents", "openai", "anthropic", "claude", "gpt", "gemini", "deepseek",
    "grok", "cursor", "copilot", "qwen", "microsoft", "google", "meta", "xai", "nvidia", "inference",
    "training", "fine-tuning", "gpu", "rag", "mcp", "model", "models", "prompt", "coding", "code",
    "机器人", "智能体", "模型", "推理", "训练", "编程", "代码", "算力", "芯片", "开源", "工作流",
)
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
WHITESPACE_RE = re.compile(r"\s+")


def clean_text(text: Any, max_chars: int | None = None) -> str:
    if text is None:
        return ""
    value = str(text).replace("\r", "\n")
    value = URL_RE.sub("", value)
    value = WHITESPACE_RE.sub(" ", value).strip()
    if max_chars and len(value) > max_chars:
        return value[: max_chars - 1].rstrip() + "…"
    return value


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_json_if_exists(path: Path) -> Any | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        return load_json(path)
    except (OSError, json.JSONDecodeError):
        return None


def expand_path(value: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(value))).resolve()


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


def ai_keyword_score(*fields: Any) -> int:
    text = " ".join(clean_text(field, max_chars=500).lower() for field in fields if field)
    return sum(1 for kw in AI_KEYWORDS if kw in text)


def engagement_score(value: Any) -> int:
    if not isinstance(value, dict):
        return 0
    likes = int(value.get("likes") or 0)
    replies = int(value.get("replies") or 0)
    retweets = int(value.get("retweets") or 0)
    return likes + replies * 2 + retweets * 2


def compute_priority(item: dict[str, Any]) -> float:
    priority = 0.0
    priority += min(ai_keyword_score(item.get("title"), item.get("summary"), item.get("source_name")) * 8, 48)
    if item.get("url"):
        priority += 18
    if item.get("has_direct_url"):
        priority += 10
    confidence = str(item.get("confidence") or "")
    priority += {"high": 18, "medium": 10, "low": 4}.get(confidence, 0)
    kind = str(item.get("kind") or "")
    priority += {
        "article_candidate": 16,
        "rss_article": 15,
        "blog_post": 14,
        "podcast_episode": 10,
        "tweet": 6,
        "newsletter": 14,
        "rss_entry": 12,
    }.get(kind, 8)
    if isinstance(item.get("score"), (int, float)):
        priority += min(float(item["score"]) / 4.0, 25)
    priority += min(engagement_score(item.get("engagement")) / 20.0, 14)
    if str(item.get("status")) == "deferred_rate_limited":
        priority -= 6
    if str(item.get("status")) == "summary_only":
        priority -= 4
    return round(priority, 2)


def compact_normalized_item(source: str, item: dict[str, Any]) -> dict[str, Any]:
    summary = clean_text(item.get("summary"), max_chars=240)
    if not summary:
        summary = clean_text(item.get("title"), max_chars=120)
    compact = {
        "source": source,
        "kind": item.get("kind") or "item",
        "title": clean_text(item.get("title"), max_chars=140),
        "url": item.get("url"),
        "summary": summary,
        "source_name": clean_text(item.get("source_name"), max_chars=80),
        "status": item.get("status") or "ready",
        "confidence": item.get("confidence") or "medium",
        "score": item.get("score"),
        "published_at": item.get("published_at") or item.get("published_local"),
        "has_direct_url": bool(item.get("has_direct_url") or item.get("url")),
        "engagement": item.get("engagement") if isinstance(item.get("engagement"), dict) else None,
    }
    compact["priority"] = compute_priority(compact)
    return compact


def collect_rss_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for feed in payload.get("feeds") or []:
        feed_name = clean_text(feed.get("name"), max_chars=80)
        category = clean_text(feed.get("category"), max_chars=60)
        for entry in feed.get("entries") or []:
            compact = {
                "source": "rss",
                "kind": "rss_entry",
                "title": clean_text(entry.get("title"), max_chars=140),
                "url": entry.get("link"),
                "summary": clean_text(entry.get("summary"), max_chars=220),
                "source_name": feed_name,
                "status": "ready",
                "confidence": "high",
                "category": category,
                "published_at": entry.get("published"),
                "has_direct_url": bool(entry.get("link")),
            }
            compact["priority"] = compute_priority(compact)
            items.append(compact)
    return items


def collect_email_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for entry in payload.get("entries") or []:
        url = entry.get("link") or entry.get("url") or entry.get("source_url")
        source_name = (
            entry.get("newsletter") or entry.get("source_name") or entry.get("from_name") or entry.get("from") or "Newsletter"
        )
        summary = (
            entry.get("summary") or entry.get("excerpt") or entry.get("body_text") or entry.get("body") or entry.get("text") or ""
        )
        title = entry.get("title") or entry.get("subject") or clean_text(summary, max_chars=80)
        compact = {
            "source": "email",
            "kind": "newsletter",
            "title": clean_text(title, max_chars=140),
            "url": url,
            "summary": clean_text(summary, max_chars=220),
            "source_name": clean_text(source_name, max_chars=80),
            "status": "ready",
            "confidence": "high" if url else "medium",
            "published_at": entry.get("date") or entry.get("published_at"),
            "has_direct_url": bool(url),
        }
        compact["priority"] = compute_priority(compact)
        items.append(compact)
    return items


def collect_normalized_items(payload: dict[str, Any], source: str) -> list[dict[str, Any]]:
    return [compact_normalized_item(source, item) for item in (payload.get("items") or []) if isinstance(item, dict)]


def select_items(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    ranked = sorted(
        items,
        key=lambda item: (
            item.get("priority") or 0,
            item.get("score") or 0,
            engagement_score(item.get("engagement")),
            item.get("title") or "",
        ),
        reverse=True,
    )
    return ranked[:limit]


def source_stats(name: str, all_items: list[dict[str, Any]], selected: list[dict[str, Any]]) -> dict[str, Any]:
    linked = sum(1 for item in all_items if item.get("url"))
    return {
        "source": name,
        "total_items": len(all_items),
        "selected_items": len(selected),
        "linked_items": linked,
        "top_priority": selected[0].get("priority") if selected else None,
    }


def build_limitations(raw_payloads: dict[str, Any]) -> list[str]:
    limitations: list[str] = []
    if not raw_payloads.get("rss"):
        limitations.append("RSS 缓存缺失或不可读。")
    rss = raw_payloads.get("rss") or {}
    rss_errors = sum(1 for feed in (rss.get("feeds") or []) if feed.get("error"))
    if rss_errors:
        limitations.append(f"RSS 有 {rss_errors} 个 feed 抓取/解析失败。")

    if not raw_payloads.get("email"):
        limitations.append("Email 缓存缺失或当日未抓到邮件。")

    bestblogs = raw_payloads.get("bestblogs") or {}
    bb_stats = bestblogs.get("stats") or {}
    if bb_stats.get("deep_read_rate_limited"):
        limitations.append(f"BestBlogs 有 {bb_stats['deep_read_rate_limited']} 条 deep-read 命中限流，已保留候选但降低优先级。")
    if bb_stats.get("items_needing_followup"):
        limitations.append(f"BestBlogs 仍有 {bb_stats['items_needing_followup']} 条需要后续补抓或人工确认。")

    ak = raw_payloads.get("ak-rss-digest") or {}
    ak_errors = ((ak.get("raw_summary") or {}).get("errors") or [])
    if ak_errors:
        limitations.append(f"AK RSS Digest 上游有 {len(ak_errors)} 个 feed 报错，但其余条目已保留。")

    follow = raw_payloads.get("follow-builders") or {}
    follow_stats = follow.get("stats") or {}
    if follow_stats.get("tweet_items"):
        limitations.append("follow-builders 含大量 X 动态，已按 AI 相关性和互动信号压缩，不保留低信噪比 tweet dump。")

    return limitations


def format_item(item: dict[str, Any]) -> str:
    bits = [f"- **{item.get('title') or '未命名条目'}**"]
    meta: list[str] = []
    if item.get("source_name"):
        meta.append(str(item["source_name"]))
    if item.get("kind"):
        meta.append(str(item["kind"]))
    if item.get("score") not in (None, ""):
        meta.append(f"score={item['score']}")
    if engagement_score(item.get("engagement")):
        meta.append(f"engagement={engagement_score(item['engagement'])}")
    if item.get("status") not in (None, "", "ready"):
        meta.append(f"status={item['status']}")
    if meta:
        bits.append("（" + " · ".join(meta) + "）")
    if item.get("summary"):
        bits.append(f"：{item['summary']}")
    if item.get("url"):
        bits.append(f" [链接]({item['url']})")
    return "".join(bits)


def build_markdown(
    *,
    date: str,
    output_dir: Path,
    cache_dir: Path,
    raw_payloads: dict[str, Any],
    selected_by_source: dict[str, list[dict[str, Any]]],
    stats_by_source: list[dict[str, Any]],
    limitations: list[str],
) -> str:
    lines = [
        f"# ai-news-keji compact context {date}",
        "",
        "## 使用说明（给 LLM）",
        "",
        "- 只用这份 compact context + summary template + filter rules 生成原始稿/摘要稿。",
        "- 不要再读取整份 raw JSON、normalized JSON、完整原始稿或整段 transcript。",
        "- 如果需要补充核验，只回到单条链接，不要把整源重新灌进上下文。",
        "",
        "## 路径",
        "",
        f"- 输出目录：`{output_dir}`",
        f"- 缓存目录：`{cache_dir}`",
        f"- 原始稿目标：`{output_dir / (date + '.md')}`",
        f"- 摘要稿目标：`{output_dir / (date + ' 摘要.md')}`",
        "",
        "## 来源统计",
        "",
    ]
    for stat in stats_by_source:
        lines.append(
            f"- {stat['source']}: total={stat['total_items']}, selected={stat['selected_items']}, linked={stat['linked_items']}"
        )
    lines.extend(["", "## 来源限制 / 风险", ""])
    if limitations:
        lines.extend(f"- {item}" for item in limitations)
    else:
        lines.append("- 无明显限制。")

    lines.extend(["", "## 候选条目（按来源压缩）", ""])
    for source, items in selected_by_source.items():
        lines.append(f"### {source}")
        lines.append("")
        if not items:
            lines.append("- 无候选条目。")
            lines.append("")
            continue
        for item in items:
            lines.append(format_item(item))
        lines.append("")

    overall = select_items([item for items in selected_by_source.values() for item in items], limit=18)
    lines.extend(["## 跨来源优先关注", ""])
    for item in overall:
        lines.append(format_item(item))
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build compact context from ai-news-keji caches")
    parser.add_argument("--date", default=None, help="Target date YYYY-MM-DD")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--output", default=None, help="Write Markdown here instead of stdout")
    parser.add_argument("--max-items-per-source", type=int, default=8)
    parser.add_argument("--max-overall-items", type=int, default=18)
    args = parser.parse_args()

    config_path = Path(args.config).expanduser()
    if not config_path.is_absolute():
        config_path = SKILL_ROOT / config_path
    config = load_yaml(config_path)
    target_date = resolve_target_date(args.date, config)
    paths = config.get("paths") or {}
    output_dir = expand_path(str(paths.get("output_dir") or "~/ai-news-keji/output"))
    cache_root = expand_path(str(paths.get("cache_dir") or "~/.cache/ai-news-keji"))
    cache_dir = cache_root / target_date

    raw_payloads = {
        "rss": load_json_if_exists(cache_dir / "rss-raw.json"),
        "email": load_json_if_exists(cache_dir / "email-raw.json"),
        "follow-builders": load_json_if_exists(cache_dir / "follow-builders-normalized.json"),
        "bestblogs": load_json_if_exists(cache_dir / "bestblogs-normalized.json"),
        "ak-rss-digest": load_json_if_exists(cache_dir / "ak-rss-digest-normalized.json"),
    }

    by_source_all = {
        "rss": collect_rss_items(raw_payloads["rss"] or {}) if raw_payloads.get("rss") else [],
        "email": collect_email_items(raw_payloads["email"] or {}) if raw_payloads.get("email") else [],
        "follow-builders": collect_normalized_items(raw_payloads["follow-builders"] or {}, "follow-builders") if raw_payloads.get("follow-builders") else [],
        "bestblogs": collect_normalized_items(raw_payloads["bestblogs"] or {}, "bestblogs") if raw_payloads.get("bestblogs") else [],
        "ak-rss-digest": collect_normalized_items(raw_payloads["ak-rss-digest"] or {}, "ak-rss-digest") if raw_payloads.get("ak-rss-digest") else [],
    }

    selected_by_source = {
        source: select_items(items, args.max_items_per_source)
        for source, items in by_source_all.items()
    }
    stats_by_source = [source_stats(source, by_source_all[source], selected_by_source[source]) for source in by_source_all]
    limitations = build_limitations(raw_payloads)

    markdown = build_markdown(
        date=target_date,
        output_dir=output_dir,
        cache_dir=cache_dir,
        raw_payloads=raw_payloads,
        selected_by_source=selected_by_source,
        stats_by_source=stats_by_source,
        limitations=limitations,
    )

    output_path = Path(args.output).expanduser().resolve() if args.output else None
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown + "\n", encoding="utf-8")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
