#!/usr/bin/env python3
"""
把外部 sources 的原始 JSON 规整成统一的中间结构，供 Agent 后续去重、评分和写稿使用。

设计目标：
- 纯规则、可重复（deterministic）
- 输出 JSON 到 stdout 或指定文件
- 不依赖 LLM
- 对重型来源先做结构化抽取，避免把超长 transcript / digest 直接带进日报
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOURCE_CHOICES = ("bestblogs", "follow-builders", "ak-rss-digest", "aihot")
URL_ONLY_RE = re.compile(r"^(https?://\S+)(\s+https?://\S+)*$", re.IGNORECASE)
WHITESPACE_RE = re.compile(r"\s+")
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def dump_json(payload: dict, output: Path | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if output is None:
        print(text)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text + "\n", encoding="utf-8")


def stable_json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def make_item_id(source: str, raw_bits: list[Any]) -> str:
    normalized_bits = [source]
    for bit in raw_bits:
        if bit is None:
            continue
        normalized_bits.append(str(bit))
    key = "|".join(normalized_bits)
    return key


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    text = text.replace("\r", "\n")
    text = WHITESPACE_RE.sub(" ", text).strip()
    return text


def clean_tweet_text(text: str | None) -> str:
    cleaned = clean_text(text)
    return cleaned


def summarize_transcript(transcript: str | None, *, max_chars: int = 400, max_segments: int = 3) -> str:
    if not transcript:
        return ""
    pieces: list[str] = []
    for raw_line in transcript.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lower().startswith("speaker "):
            parts = line.split("-", 1)
            if len(parts) == 2:
                line = parts[1].strip()
        line = clean_text(line)
        if not line:
            continue
        pieces.append(line)
        if len(pieces) >= max_segments:
            break
    summary = " ".join(pieces)
    if len(summary) > max_chars:
        summary = summary[: max_chars - 1].rstrip() + "…"
    return summary


def load_bestblogs_deep(resource_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """返回 (meta, error_info)。error_info 非空表示 deep-read 失败或限流。"""
    try:
        result = subprocess.run(
            ["bestblogs", "read", "deep", resource_id, "--json"],
            capture_output=True,
            text=True,
            timeout=45,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, {"status": "command_error", "message": str(exc)}

    stdout = result.stdout or ""
    stderr = result.stderr or ""

    payload = None
    if stdout.strip():
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = None

    data = payload.get("data") if isinstance(payload, dict) else None
    meta = data.get("meta") if isinstance(data, dict) else None
    if isinstance(meta, dict):
        return meta, None

    combined = f"{stdout}\n{stderr}".upper()
    if "RATE_LIMITED" in combined or "429" in combined:
        return None, {
            "status": "rate_limited",
            "message": (stderr or stdout or "BestBlogs deep read rate limited").strip(),
        }

    if result.returncode != 0:
        return None, {
            "status": "nonzero_exit",
            "returncode": result.returncode,
            "message": (stderr or stdout or "bestblogs read deep failed").strip(),
        }

    if stdout.strip() and payload is None:
        return None, {"status": "invalid_json", "message": "BestBlogs deep-read stdout is not valid JSON"}

    return None, {"status": "missing_meta", "message": "BestBlogs deep-read JSON missing data.meta"}


def normalize_bestblogs(
    payload: dict[str, Any],
    *,
    deep_read: bool = False,
    deep_read_limit: int = 10,
) -> dict[str, Any]:
    data = payload.get("data") or {}
    candidates = data.get("candidates") or []
    items: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    deep_read_attempted = 0
    deep_read_completed = 0
    deep_read_rate_limited = 0

    for idx, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            dropped.append({
                "index": idx,
                "reason": "candidate_not_object",
                "raw_preview": str(candidate)[:200],
            })
            continue

        title = clean_text(candidate.get("title"))
        summary = clean_text(candidate.get("selectionReason"))
        resource_id = candidate.get("resourceId")
        read_url = candidate.get("readUrl")
        source_name = clean_text(candidate.get("sourceName"))
        score = candidate.get("score")
        language = candidate.get("language")
        item_status = "ready"
        canonical_url = read_url
        deep_read_meta = None
        deep_read_error = None
        confidence = "high" if read_url else "medium"

        if not title:
            dropped.append({
                "index": idx,
                "reason": "missing_title",
                "resource_id": resource_id,
            })
            continue

        if not summary:
            summary = title

        if not canonical_url and resource_id:
            item_status = "needs_deep_read"

        if deep_read and resource_id and not canonical_url and deep_read_attempted < deep_read_limit:
            deep_read_attempted += 1
            deep_read_meta, deep_read_error = load_bestblogs_deep(str(resource_id))
            if deep_read_meta:
                deep_read_completed += 1
                canonical_url = deep_read_meta.get("url") or deep_read_meta.get("readUrl") or canonical_url
                summary = clean_text(
                    deep_read_meta.get("oneSentenceSummary")
                    or deep_read_meta.get("summary")
                    or deep_read_meta.get("featuredReason")
                    or summary
                )
                item_status = "ready" if canonical_url else "summary_only"
                confidence = "high" if canonical_url else "medium"
            elif deep_read_error and deep_read_error.get("status") == "rate_limited":
                deep_read_rate_limited += 1
                item_status = "deferred_rate_limited"
                confidence = "medium"
            else:
                item_status = "summary_only"
                confidence = "medium"
        elif not canonical_url:
            item_status = "summary_only" if not resource_id else item_status

        item = {
            "id": make_item_id("bestblogs", [resource_id or idx, title]),
            "source": "bestblogs",
            "kind": "article_candidate",
            "title": title,
            "url": canonical_url,
            "bestblogs_read_url": candidate.get("readUrl"),
            "summary": summary,
            "source_name": source_name,
            "score": score,
            "language": language,
            "resource_id": resource_id,
            "status": item_status,
            "confidence": confidence,
            "has_direct_url": bool(canonical_url),
            "candidate_source": candidate.get("candidateSource"),
            "fallback_applied": bool(candidate.get("fallbackApplied")),
            "personalized": bool(candidate.get("personalized")),
            "raw_candidate": candidate,
        }
        if deep_read_meta:
            item["deep_read"] = {
                "source_name": deep_read_meta.get("sourceName"),
                "canonical_url": deep_read_meta.get("url"),
                "bestblogs_read_url": deep_read_meta.get("readUrl"),
                "one_sentence_summary": deep_read_meta.get("oneSentenceSummary"),
                "featured_reason": deep_read_meta.get("featuredReason"),
                "authors": deep_read_meta.get("authors"),
                "tags": deep_read_meta.get("tags"),
                "publish_datetime": deep_read_meta.get("publishDateTimeStr"),
                "qualified": deep_read_meta.get("qualified"),
                "process_status": deep_read_meta.get("processFlowStatus"),
            }
        if deep_read_error:
            item["deep_read_error"] = deep_read_error
        items.append(item)

    return {
        "schema_version": 1,
        "normalized_at": now_iso(),
        "source": "bestblogs",
        "raw_summary": {
            "success": payload.get("success"),
            "primary_source": data.get("primarySource"),
            "fallback_applied": bool(data.get("fallbackApplied")),
            "tried_sources": (data.get("details") or {}).get("triedSources") or [],
        },
        "items": items,
        "dropped": dropped,
        "stats": {
            "candidate_count": len(candidates),
            "normalized_items": len(items),
            "dropped_items": len(dropped),
            "items_with_direct_url": sum(1 for item in items if item.get("has_direct_url")),
            "items_needing_followup": sum(1 for item in items if item.get("status") in {"needs_deep_read", "deferred_rate_limited", "summary_only"}),
            "deep_read_attempted": deep_read_attempted,
            "deep_read_completed": deep_read_completed,
            "deep_read_rate_limited": deep_read_rate_limited,
        },
    }


def normalize_follow_builders(payload: dict[str, Any]) -> dict[str, Any]:
    podcasts = payload.get("podcasts") or []
    builders = payload.get("x") or []
    blogs = payload.get("blogs") or []
    items: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []

    for idx, podcast in enumerate(podcasts):
        if not isinstance(podcast, dict):
            dropped.append({"kind": "podcast", "index": idx, "reason": "podcast_not_object"})
            continue
        title = clean_text(podcast.get("title"))
        url = podcast.get("url")
        if not title or not url:
            dropped.append({
                "kind": "podcast",
                "index": idx,
                "reason": "missing_title_or_url",
                "title": title,
                "url": url,
            })
            continue
        transcript = podcast.get("transcript") or ""
        items.append({
            "id": make_item_id("follow-builders", ["podcast", podcast.get("guid"), title]),
            "source": "follow-builders",
            "kind": "podcast_episode",
            "title": title,
            "url": url,
            "summary": summarize_transcript(transcript),
            "published_at": podcast.get("publishedAt"),
            "source_name": clean_text(podcast.get("name")),
            "status": "ready" if summarize_transcript(transcript) else "needs_review",
            "confidence": "medium",
            "transcript_present": bool(transcript),
            "transcript_chars": len(transcript),
            "raw_ref": {
                "guid": podcast.get("guid"),
                "source": podcast.get("source"),
            },
        })

    for idx, builder in enumerate(builders):
        if not isinstance(builder, dict):
            dropped.append({"kind": "x_builder", "index": idx, "reason": "builder_not_object"})
            continue
        builder_name = clean_text(builder.get("name"))
        handle = clean_text(builder.get("handle"))
        bio = clean_text(builder.get("bio"))
        tweets = builder.get("tweets") or []
        for tweet_idx, tweet in enumerate(tweets):
            if not isinstance(tweet, dict):
                dropped.append({
                    "kind": "x_tweet",
                    "builder": builder_name or handle,
                    "index": tweet_idx,
                    "reason": "tweet_not_object",
                })
                continue
            text = clean_tweet_text(tweet.get("text"))
            url = tweet.get("url")
            if not url:
                dropped.append({
                    "kind": "x_tweet",
                    "builder": builder_name or handle,
                    "index": tweet_idx,
                    "reason": "missing_url",
                })
                continue
            visible_text = URL_RE.sub("", text).strip()
            if not visible_text or URL_ONLY_RE.match(text):
                dropped.append({
                    "kind": "x_tweet",
                    "builder": builder_name or handle,
                    "index": tweet_idx,
                    "reason": "url_only_or_empty_text",
                    "url": url,
                })
                continue
            items.append({
                "id": make_item_id("follow-builders", ["tweet", tweet.get("id"), handle]),
                "source": "follow-builders",
                "kind": "tweet",
                "title": f"{builder_name or handle}：{visible_text[:80]}" + ("…" if len(visible_text) > 80 else ""),
                "url": url,
                "summary": text,
                "published_at": tweet.get("createdAt"),
                "source_name": builder_name,
                "author_handle": handle,
                "author_bio": bio,
                "status": "ready",
                "confidence": "medium",
                "engagement": {
                    "likes": tweet.get("likes"),
                    "retweets": tweet.get("retweets"),
                    "replies": tweet.get("replies"),
                },
                "is_quote": bool(tweet.get("isQuote")),
                "quoted_tweet_id": tweet.get("quotedTweetId"),
                "raw_ref": {
                    "tweet_id": tweet.get("id"),
                    "source": tweet.get("source") or builder.get("source"),
                },
            })

    for idx, blog in enumerate(blogs):
        if not isinstance(blog, dict):
            dropped.append({"kind": "blog", "index": idx, "reason": "blog_not_object"})
            continue
        raw_posts = blog.get("posts")
        posts = raw_posts if isinstance(raw_posts, list) else [blog]
        for post_idx, post in enumerate(posts):
            if not isinstance(post, dict):
                dropped.append({
                    "kind": "blog_post",
                    "index": post_idx,
                    "reason": "blog_post_not_object",
                })
                continue
            title = clean_text(post.get("title"))
            url = post.get("url") or post.get("link")
            summary = clean_text(post.get("summary") or post.get("description") or post.get("content"))
            if not title or not url:
                dropped.append({
                    "kind": "blog_post",
                    "index": post_idx,
                    "reason": "missing_title_or_url",
                })
                continue
            items.append({
                "id": make_item_id("follow-builders", ["blog", title, url]),
                "source": "follow-builders",
                "kind": "blog_post",
                "title": title,
                "url": url,
                "summary": summary[:400] + ("…" if len(summary) > 400 else ""),
                "published_at": post.get("publishedAt") or post.get("published_at"),
                "source_name": clean_text(post.get("blogName") or post.get("sourceName") or blog.get("name")),
                "status": "ready",
                "confidence": "medium",
                "raw_ref": {
                    "source": post.get("source") or blog.get("source"),
                },
            })

    return {
        "schema_version": 1,
        "normalized_at": now_iso(),
        "source": "follow-builders",
        "raw_summary": {
            "status": payload.get("status"),
            "generated_at": payload.get("generatedAt"),
            "config": payload.get("config") or {},
            "stats": payload.get("stats") or {},
        },
        "items": items,
        "dropped": dropped,
        "stats": {
            "normalized_items": len(items),
            "dropped_items": len(dropped),
            "podcast_items": sum(1 for item in items if item.get("kind") == "podcast_episode"),
            "tweet_items": sum(1 for item in items if item.get("kind") == "tweet"),
            "blog_items": sum(1 for item in items if item.get("kind") == "blog_post"),
        },
    }


def normalize_ak_rss_digest(payload: dict[str, Any]) -> dict[str, Any]:
    raw_items = payload.get("items") or []
    raw_errors = payload.get("errors") or []
    items: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []

    for idx, entry in enumerate(raw_items):
        if not isinstance(entry, dict):
            dropped.append({"index": idx, "reason": "item_not_object"})
            continue
        title = clean_text(entry.get("title"))
        url = entry.get("link")
        summary = clean_text(entry.get("summary"))
        if not title or not url:
            dropped.append({
                "index": idx,
                "reason": "missing_title_or_url",
                "title": title,
                "url": url,
            })
            continue
        items.append({
            "id": make_item_id("ak-rss-digest", [entry.get("feed_name"), title, url]),
            "source": "ak-rss-digest",
            "kind": "rss_article",
            "title": title,
            "url": url,
            "summary": summary,
            "published_at": entry.get("published_at"),
            "published_local": entry.get("published_local"),
            "source_name": clean_text(entry.get("feed_name")),
            "site_url": entry.get("site_url"),
            "feed_url": entry.get("feed_url"),
            "status": "ready",
            "confidence": "high",
            "raw_ref": {
                "published_raw": entry.get("published_raw"),
            },
        })

    return {
        "schema_version": 1,
        "normalized_at": now_iso(),
        "source": "ak-rss-digest",
        "raw_summary": {
            "start_date": payload.get("start_date"),
            "target_date": payload.get("target_date"),
            "days": payload.get("days"),
            "timezone": payload.get("timezone"),
            "feed_count": payload.get("feed_count"),
            "errors": raw_errors,
        },
        "items": items,
        "dropped": dropped,
        "stats": {
            "normalized_items": len(items),
            "dropped_items": len(dropped),
            "upstream_errors": len(raw_errors),
        },
    }


def normalize_aihot(payload: dict[str, Any]) -> dict[str, Any]:
    raw_items = payload.get("items") or []
    items: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []

    for idx, entry in enumerate(raw_items):
        if not isinstance(entry, dict):
            dropped.append({"index": idx, "reason": "item_not_object"})
            continue

        title = clean_text(entry.get("title"))
        url = entry.get("url")
        summary = clean_text(entry.get("summary"))
        source_name = clean_text(entry.get("source"))
        if not title or not url:
            dropped.append({
                "index": idx,
                "reason": "missing_title_or_url",
                "id": entry.get("id"),
                "title": title,
                "url": url,
            })
            continue

        selected = bool(entry.get("selected"))
        items.append({
            "id": make_item_id("aihot", [entry.get("id") or url, title]),
            "source": "aihot",
            "kind": "aihot_item",
            "title": title,
            "title_en": clean_text(entry.get("title_en")),
            "url": url,
            "summary": summary,
            "published_at": entry.get("publishedAt"),
            "source_name": source_name or "AI HOT",
            "category": entry.get("category"),
            "score": entry.get("score"),
            "selected": selected,
            "status": "ready",
            "confidence": "high" if selected else "medium",
            "has_direct_url": True,
            "raw_ref": {
                "id": entry.get("id"),
                "source": "AI HOT",
            },
        })

    return {
        "schema_version": 1,
        "normalized_at": now_iso(),
        "source": "aihot",
        "raw_summary": {
            "target_date": payload.get("target_date"),
            "timezone": payload.get("timezone"),
            "request": payload.get("request") or {},
            "response": payload.get("response") or {},
            "stats": payload.get("stats") or {},
        },
        "items": items,
        "dropped": dropped + (payload.get("dropped") or []),
        "stats": {
            "normalized_items": len(items),
            "dropped_items": len(dropped) + len(payload.get("dropped") or []),
            "items_with_direct_url": len(items),
            "selected_items": sum(1 for item in items if item.get("selected")),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize heavy external-source outputs into a common JSON schema")
    parser.add_argument("--source", required=True, choices=SOURCE_CHOICES)
    parser.add_argument("--input", required=True, help="Path to raw JSON file")
    parser.add_argument("--output", default=None, help="Write normalized JSON here instead of stdout")
    parser.add_argument("--deep-read-bestblogs", action="store_true", help="For BestBlogs, try `bestblogs read deep` on URL-less candidates")
    parser.add_argument("--deep-read-limit", type=int, default=10, help="Max BestBlogs deep-read attempts")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve() if args.output else None
    payload = load_json(input_path)

    if args.source == "bestblogs":
        normalized = normalize_bestblogs(
            payload,
            deep_read=args.deep_read_bestblogs,
            deep_read_limit=max(args.deep_read_limit, 0),
        )
    elif args.source == "follow-builders":
        normalized = normalize_follow_builders(payload)
    elif args.source == "ak-rss-digest":
        normalized = normalize_ak_rss_digest(payload)
    elif args.source == "aihot":
        normalized = normalize_aihot(payload)
    else:
        raise AssertionError(f"unsupported source: {args.source}")

    normalized["input_path"] = str(input_path)
    normalized["output_path"] = str(output_path) if output_path else None
    normalized["fingerprint"] = make_item_id(args.source, [stable_json_dumps(normalized.get("stats")), len(normalized.get("items") or [])])
    dump_json(normalized, output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
