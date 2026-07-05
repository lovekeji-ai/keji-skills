#!/usr/bin/env python3
"""
检查当前环境是否已经可以运行 ai-news-keji。
"""
from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from _runtime import missing_modules

try:
    import yaml
except ImportError:
    yaml = None


SKILL_ROOT = Path(__file__).resolve().parent.parent
PRIVATE_PATTERNS = tuple(
    pattern
    for pattern in (
        str(Path.home()),
        Path.home().name,
        "Second" + " Brain",
    )
    if pattern
)
PUBLIC_FILES = (
    "SKILL.md",
    "README.md",
    "config.example.yaml",
    "sources.example.yaml",
    "requirements.txt",
    "scripts/init.py",
    "scripts/init_wizard.py",
    "scripts/check-run-state.py",
    "scripts/build-summary-context.py",
    "scripts/fetch-aihot.py",
    "scripts/normalize-external-source.py",
    "scripts/sync-hermes-skill.sh",
    "scripts/fetch-email-imap.py",
    "scripts/fetch-rss.py",
    "scripts/doctor.py",
    "prompts/summary-template.md",
    "references/filter-rules.example.md",
    "agents/openai.yaml",
)


def status(kind: str, message: str) -> None:
    print(f"[{kind}] {message}")


def has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def load_yaml(path: Path) -> dict:
    if yaml is None:
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def check_required_files() -> int:
    problems = 0
    for relative in PUBLIC_FILES:
        path = SKILL_ROOT / relative
        if path.exists():
            status("ok", f"找到 {relative}")
        else:
            status("error", f"缺少 {relative}")
            problems += 1
    return problems


def check_python_dependencies() -> int:
    problems = 0
    missing = set(missing_modules(["yaml", "feedparser"]))
    for module, package in (("yaml", "PyYAML"), ("feedparser", "feedparser")):
        if module not in missing:
            status("ok", f"Python 模块可用：{module}")
        else:
            status("error", f"缺少 Python 包：{package}。请运行：.venv/bin/python -m pip install -r requirements.txt")
            problems += 1
    return problems


def check_local_config() -> int:
    problems = 0
    config_path = SKILL_ROOT / "config.yaml"
    sources_path = SKILL_ROOT / "sources.yaml"

    if config_path.exists():
        status("ok", "本地 config.yaml 存在")
        if yaml is not None:
            config = load_yaml(config_path)
            check_setup_config(config)
            paths = config.get("paths", {})
            for key in ("output_dir", "cache_dir"):
                raw = paths.get(key)
                if not raw:
                    status("warn", f"未设置 paths.{key}")
                    continue
                expanded = Path(os.path.expandvars(os.path.expanduser(str(raw))))
                if expanded.exists():
                    status("ok", f"paths.{key} 存在：{expanded}")
                else:
                    status("warn", f"paths.{key} 尚不存在：{expanded}")
            filter_rules = paths.get("filter_rules")
            if filter_rules:
                expanded = Path(os.path.expandvars(os.path.expanduser(str(filter_rules))))
                if expanded.exists():
                    status("ok", f"paths.filter_rules 存在：{expanded}")
                else:
                    status("warn", "缺少 paths.filter_rules；将使用内置示例规则")
            check_email_config(config)
            check_external_skills(config)
    else:
        status("warn", "缺少 config.yaml。请把 config.example.yaml 复制为 config.yaml，并编辑本地路径。")

    if sources_path.exists():
        status("ok", "本地 sources.yaml 存在")
    else:
        status("warn", "缺少 sources.yaml。RSS 抓取脚本会回退到 sources.example.yaml。")

    if platform.system() != "Darwin":
        status("info", "当前平台不可用 macOS 通知；请使用 notification.method: none")

    return problems


def check_email_config(config: dict) -> None:
    pipeline = config.get("pipeline", {})
    enabled_sources = pipeline.get("enabled_sources") or []
    email_config = config.get("email") or {}
    mode = email_config.get("mode", "none")

    if mode == "none" and "email" not in enabled_sources:
        status("info", "email 来源已关闭")
        return

    if mode == "imap":
        imap_config = email_config.get("imap") or {}
        host = imap_config.get("host")
        username_env = imap_config.get("username_env") or "AI_NEWS_IMAP_USERNAME"
        password_env = imap_config.get("password_env") or "AI_NEWS_IMAP_PASSWORD"

        if host:
            status("ok", f"email.imap.host 已配置：{host}")
        else:
            status("warn", "email.mode 为 imap，但缺少 email.imap.host")

        if os.environ.get(username_env):
            status("ok", f"IMAP 账号环境变量已设置：{username_env}")
        else:
            status("warn", f"未设置 IMAP 账号环境变量：{username_env}")

        if os.environ.get(password_env):
            status("ok", f"IMAP 密码/授权码环境变量已设置：{password_env}")
        else:
            status("warn", f"未设置 IMAP 密码/授权码环境变量：{password_env}")
        return

    if mode == "mcp":
        status("info", "email.mode 为 mcp；请确认当前 Agent 运行环境提供 email/Gmail MCP 工具")
        return

    if "email" in enabled_sources:
        status("warn", f"已启用 email 来源，但 email.mode 是 {mode!r}；应为 none、imap 或 mcp")


def check_setup_config(config: dict) -> None:
    setup = config.get("setup") or {}
    if setup.get("initialized") is True:
        status("ok", "setup.initialized 为 true")
    else:
        status("warn", "setup.initialized 不是 true；请运行：python3 scripts/init.py")

    version = setup.get("init_schema_version")
    if version:
        status("ok", f"setup.init_schema_version: {version}")
    else:
        status("warn", "缺少 setup.init_schema_version")


def check_external_skills(config: dict) -> None:
    external_config = config.get("external_skills") or {}
    if not external_config:
        status("info", "未配置外部 skills")
        return

    install_dir = external_config.get("install_dir")
    if install_dir:
        expanded = Path(os.path.expandvars(os.path.expanduser(str(install_dir))))
        if expanded.exists():
            status("ok", f"external_skills.install_dir 存在：{expanded}")
        else:
            status("warn", f"external_skills.install_dir 不存在：{expanded}")

    link_targets = external_config.get("link_targets") or []
    for target in link_targets:
        expanded = Path(os.path.expandvars(os.path.expanduser(str(target))))
        if expanded.exists():
            status("ok", f"外部 skill 软链目标存在：{expanded}")
        else:
            status("warn", f"外部 skill 软链目标不存在：{expanded}")

    enabled = []
    for name, item in external_config.items():
        if not isinstance(item, dict):
            continue
        if item.get("enabled"):
            enabled.append(name)
            command = item.get("command")
            if command:
                status("ok", f"外部 skill 已启用：{name}")
            else:
                status("warn", f"外部 skill {name} 已启用，但缺少 command")

            install_path = item.get("install_path")
            if install_path:
                expanded = Path(os.path.expandvars(os.path.expanduser(str(install_path))))
                if expanded.exists():
                    status("ok", f"{name} install_path 存在：{expanded}")
                else:
                    status("warn", f"{name} install_path 不存在：{expanded}")

            if name == "bestblogs":
                check_bestblogs_auth()

    if not enabled:
        status("info", "外部 skills 已关闭")


def check_bestblogs_auth() -> None:
    if not shutil.which("bestblogs"):
        status("warn", "bestblogs 已启用但找不到 bestblogs 命令；请运行 python3 scripts/init.py --skills bestblogs")
        return
    try:
        result = subprocess.run(
            ["bestblogs", "auth", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        status("warn", f"调用 bestblogs auth status 失败：{exc}")
        return
    if result.returncode != 0:
        status("warn", "bestblogs auth status 返回非零；请运行 bestblogs auth status 排查")
        return
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        status("warn", "bestblogs auth status 输出非 JSON；请检查 BestBlogs CLI 版本")
        return
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict) and data.get("loggedIn"):
        status("ok", "BestBlogs 已登录")
    else:
        status("warn", "BestBlogs 未登录；未登录时 discover 接口返回空数据。请运行：bestblogs auth login")


def check_publish_safety() -> int:
    problems = 0
    for relative in PUBLIC_FILES:
        path = SKILL_ROOT / relative
        if not path.exists() or path.is_dir():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in PRIVATE_PATTERNS:
            if pattern in text:
                status("error", f"在 {relative} 中发现疑似私人路径/信息：{pattern!r}")
                problems += 1
    return problems


def main() -> int:
    print(f"ai-news-keji doctor: {SKILL_ROOT}")
    problems = 0

    problems += check_required_files()
    problems += check_python_dependencies()
    problems += check_local_config()
    problems += check_publish_safety()

    if problems:
        status("error", f"有 {problems} 个问题需要处理")
        return 1

    status("ok", "doctor 检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
