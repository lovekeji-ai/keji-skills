#!/usr/bin/env python3
"""
检查某个目标日期是否已经存在 ai-news-keji 运行产物。

输出 JSON 到 stdout，供 Agent 在抓取前决定是否需要先询问用户，
并识别“只跑了一半”的日期目录（例如只有 raw cache、没有摘要稿，
或者 heavy external sources 还没完成 deterministic normalization）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from _runtime import ensure_modules

ensure_modules(["yaml"])

try:
    import yaml
except ImportError:
    print("错误：未安装 PyYAML。请在仓库根目录运行：.venv/bin/python -m pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)


SKILL_ROOT = Path(__file__).resolve().parent.parent
RAW_CACHE_FILE_NAMES = {
    "email-raw.json": "email",
    "rss-raw.json": "rss",
    "external-skills.json": "external_skills",
    "websites.json": "websites",
    "follow-builders.json": "follow-builders",
    "bestblogs.json": "bestblogs",
    "ak-rss.json": "ak-rss-digest",
    "ak-rss-raw.json": "ak-rss-digest",
    "aihot.json": "aihot",
    "aihot-raw.json": "aihot",
}
NORMALIZED_CACHE_FILE_NAMES = {
    "follow-builders-normalized.json": "follow-builders",
    "bestblogs-normalized.json": "bestblogs",
    "ak-rss-digest-normalized.json": "ak-rss-digest",
    "aihot-normalized.json": "aihot",
    "external-skills-normalized.json": "external_skills",
}
MANIFEST_FILE_NAMES = {
    "run-manifest.json",
    "run-metadata.json",
}


HEAVY_EXTERNAL_SOURCES = ("follow-builders", "bestblogs", "ak-rss-digest", "aihot")
EXTERNAL_SKILL_HEAVY_SOURCES = ("follow-builders", "bestblogs", "ak-rss-digest")
GROUP_SOURCES = ("rss", "email", "external_skills", "websites")
ALL_SOURCES = GROUP_SOURCES + HEAVY_EXTERNAL_SOURCES
MANIFEST_COMPLETE_STATUSES = {"complete", "completed", "ready"}


def expand_path(value: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(value))).resolve()


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_json_if_exists(path: Path) -> dict | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


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


def file_state(path: Path) -> dict:
    exists = path.exists()
    state = {
        "path": str(path),
        "exists": exists,
    }
    if exists and path.is_file():
        stat = path.stat()
        state.update({
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        })
    return state


def cache_state(path: Path) -> dict:
    state = {
        "path": str(path),
        "exists": path.exists(),
        "files": [],
        "known_raw_files": [],
        "known_normalized_files": [],
        "manifest_files": [],
        "unknown_files": [],
    }
    if not path.exists() or not path.is_dir():
        return state

    for item in sorted(path.iterdir()):
        if not item.is_file():
            continue
        stat = item.stat()
        entry = {
            "name": item.name,
            "path": str(item),
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        }
        state["files"].append(entry)
        if item.name in RAW_CACHE_FILE_NAMES:
            state["known_raw_files"].append(item.name)
        elif item.name in NORMALIZED_CACHE_FILE_NAMES:
            state["known_normalized_files"].append(item.name)
        elif item.name in MANIFEST_FILE_NAMES:
            state["manifest_files"].append(item.name)
        else:
            state["unknown_files"].append(item.name)
    return state


def source_state_template(name: str) -> dict:
    return {
        "name": name,
        "raw_files": [],
        "normalized_files": [],
        "manifest": None,
        "has_raw": False,
        "has_normalized": False,
        "is_heavy_external": name in HEAVY_EXTERNAL_SOURCES,
        "is_complete": False,
        "status": "missing",
        "notes": [],
    }


def manifest_indicates_complete(state: dict) -> bool:
    manifest = state.get("manifest") or {}
    manifest_status = str(manifest.get("status") or "").lower()
    return bool(manifest.get("completed")) or manifest_status in MANIFEST_COMPLETE_STATUSES


def source_has_signal(state: dict) -> bool:
    return bool(state["has_raw"] or state["has_normalized"] or state.get("manifest"))


def build_source_states(cache_dir: Path, daily_cache: dict) -> dict[str, dict]:
    states = {name: source_state_template(name) for name in ALL_SOURCES}

    for file_name in daily_cache.get("known_raw_files") or []:
        source_name = RAW_CACHE_FILE_NAMES.get(file_name)
        if source_name:
            states[source_name]["raw_files"].append(file_name)
            states[source_name]["has_raw"] = True
            if source_name in EXTERNAL_SKILL_HEAVY_SOURCES:
                states["external_skills"]["raw_files"].append(file_name)
                states["external_skills"]["has_raw"] = True

    for file_name in daily_cache.get("known_normalized_files") or []:
        source_name = NORMALIZED_CACHE_FILE_NAMES.get(file_name)
        if source_name:
            states[source_name]["normalized_files"].append(file_name)
            states[source_name]["has_normalized"] = True
            if source_name in EXTERNAL_SKILL_HEAVY_SOURCES:
                states["external_skills"]["normalized_files"].append(file_name)
                states["external_skills"]["has_normalized"] = True

    manifest_payload = None
    manifest_path = None
    for file_name in daily_cache.get("manifest_files") or []:
        candidate = cache_dir / file_name
        payload = load_json_if_exists(candidate)
        if payload:
            manifest_payload = payload
            manifest_path = candidate
            break

    if manifest_payload:
        raw_manifest_sources = manifest_payload.get("sources")
        manifest_sources = raw_manifest_sources if isinstance(raw_manifest_sources, dict) else {}
        for name, source_manifest in manifest_sources.items():
            if name not in states or not isinstance(source_manifest, dict):
                continue
            states[name]["manifest"] = {
                "path": str(manifest_path),
                "status": source_manifest.get("status"),
                "completed": source_manifest.get("completed"),
                "item_count": source_manifest.get("item_count"),
                "notes": source_manifest.get("notes"),
            }

    for name, state in states.items():
        manifest_complete = manifest_indicates_complete(state)
        if state["is_heavy_external"]:
            if state["has_raw"] and state["has_normalized"]:
                state["is_complete"] = True
                state["status"] = "complete"
            elif state["has_raw"] and not state["has_normalized"]:
                state["is_complete"] = False
                state["status"] = "raw_only"
                state["notes"].append("存在 raw cache，但尚未完成 deterministic normalization")
                if manifest_complete:
                    state["notes"].append("manifest 标记完成，但 heavy external source 仍缺少 normalized 文件")
            elif state["has_normalized"] and not state["has_raw"]:
                state["is_complete"] = False
                state["status"] = "normalized_only"
                state["notes"].append("存在 normalized 文件，但缺少对应 raw cache")
                if manifest_complete:
                    state["notes"].append("manifest 标记完成，但 heavy external source 仍缺少 raw cache")
            elif manifest_complete:
                state["is_complete"] = True
                state["status"] = "complete"
                state["notes"].append("manifest 标记来源已完成，未发现 raw/normalized cache 文件")
            else:
                state["is_complete"] = False
                state["status"] = "missing"
        else:
            state["is_complete"] = bool(state["has_raw"] or manifest_complete)
            if state["is_complete"]:
                state["status"] = "complete"
                if manifest_complete and not state["has_raw"]:
                    state["notes"].append("manifest 标记来源已完成，未发现 raw cache 文件")
            else:
                state["status"] = "missing"

    heavy_states = [states[name] for name in EXTERNAL_SKILL_HEAVY_SOURCES if source_has_signal(states[name])]
    if heavy_states:
        states["external_skills"]["is_complete"] = bool(heavy_states) and all(item["is_complete"] for item in heavy_states)
        if states["external_skills"]["is_complete"]:
            states["external_skills"]["status"] = "complete"
        elif any(item["status"] == "raw_only" for item in heavy_states):
            states["external_skills"]["status"] = "raw_only"
            states["external_skills"]["notes"].append("至少一个 heavy external source 只有 raw cache，没有 normalized 中间层")
        else:
            states["external_skills"]["status"] = "partial"
            states["external_skills"]["notes"].append("external_skills 组内各 source 完成度不一致")

    return states


def summarize_partial_reasons(raw_note: dict, summary_note: dict, daily_cache: dict, source_states: dict[str, dict]) -> list[str]:
    reasons: list[str] = []
    cache_exists = bool(daily_cache.get("exists") and daily_cache.get("files"))
    if cache_exists and not raw_note["exists"]:
        reasons.append("已存在缓存，但原始稿缺失")
    if raw_note["exists"] and not summary_note["exists"]:
        reasons.append("原始稿已存在，但摘要稿缺失")
    if cache_exists and not summary_note["exists"]:
        reasons.append("已存在缓存，但摘要稿尚未生成")

    for source_name in HEAVY_EXTERNAL_SOURCES:
        state = source_states[source_name]
        if state["status"] == "raw_only":
            reasons.append(f"{source_name} 只有 raw cache，尚未完成 normalization")
        elif state["status"] == "normalized_only":
            reasons.append(f"{source_name} 只有 normalized 文件，缺少 raw cache")

    return reasons


def main() -> int:
    parser = argparse.ArgumentParser(description="Check existing ai-news-keji outputs and cache for a target date")
    parser.add_argument("--date", default=None, help="Target date YYYY-MM-DD (default follows config settings.default_date)")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    args = parser.parse_args()

    config_path = Path(args.config).expanduser()
    if not config_path.is_absolute():
        config_path = SKILL_ROOT / config_path
    if not config_path.exists():
        print(f"错误：缺少配置文件：{config_path}", file=sys.stderr)
        return 1

    config = load_yaml(config_path)
    target_date = resolve_target_date(args.date, config)
    paths = config.get("paths") or {}
    output_dir = expand_path(str(paths.get("output_dir") or "~/ai-news-keji/output"))
    cache_dir = expand_path(str(paths.get("cache_dir") or "~/.cache/ai-news-keji"))

    raw_note = file_state(output_dir / f"{target_date}.md")
    summary_note = file_state(output_dir / f"{target_date} 摘要.md")
    daily_cache_dir = cache_dir / target_date
    daily_cache = cache_state(daily_cache_dir)
    source_states = build_source_states(daily_cache_dir, daily_cache)

    existing_kinds = []
    if raw_note["exists"]:
        existing_kinds.append("raw_note")
    if summary_note["exists"]:
        existing_kinds.append("summary_note")
    if daily_cache["exists"] and daily_cache["files"]:
        existing_kinds.append("cache")

    partial_reasons = summarize_partial_reasons(raw_note, summary_note, daily_cache, source_states)
    has_existing = bool(existing_kinds)
    is_partial_run = bool(partial_reasons)

    recommended_action = "fresh_run"
    if has_existing and is_partial_run:
        recommended_action = "ask_user_incremental_or_overwrite"
    elif has_existing:
        recommended_action = "ask_user_use_existing_or_overwrite"

    print(json.dumps({
        "date": target_date,
        "output_dir": str(output_dir),
        "cache_dir": str(cache_dir),
        "raw_note": raw_note,
        "summary_note": summary_note,
        "daily_cache": daily_cache,
        "source_states": source_states,
        "existing_kinds": existing_kinds,
        "has_existing": has_existing,
        "is_partial_run": is_partial_run,
        "partial_reasons": partial_reasons,
        "recommended_action": recommended_action,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
