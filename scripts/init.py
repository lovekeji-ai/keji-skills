#!/usr/bin/env python3
"""
初始化 ai-news-keji 的本地运行环境。

这个脚本会创建本地配置文件、记录初始化状态，并可选择安装外部
skills 到受管理目录，再软链到 Claude/Codex 的 skill 目录。
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from _runtime import ensure_modules

ensure_modules(["yaml"])

try:
    import yaml
except ImportError:
    print("错误：未安装 PyYAML。请在仓库根目录运行：.venv/bin/python -m pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)

from init_wizard import (
    add_enabled_source,
    apply_guided_answers,
    apply_newsletter_answer,
    apply_output_dir_answer,
    apply_preferences_answer,
    mark_setup_step,
    remove_enabled_source,
    print_agent_setup_flow,
    print_reconfigure_flow,
    prompt_yes_no,
    setup_steps,
)


RECONFIGURE_SECTIONS = ("external_skills", "newsletter", "output_dir", "preferences")


SKILL_ROOT = Path(__file__).resolve().parent.parent
SETUP_SCHEMA_VERSION = 1
DEFAULT_INSTALL_DIR = "~/.local/share/ai-news-keji/external-skills"
DEFAULT_LINK_TARGETS = ["~/.claude/skills"]

EXTERNAL_SKILLS = {
    "follow-builders": {
        "label": "follow-builders",
        "description": "聚合 X、播客和官方 AI 博客里的 AI builder 动态。",
        "repo": "https://github.com/zarazhangrui/follow-builders.git",
        "install_kind": "git-node-skill",
        "clone_dir": "follow-builders",
        "link_name": "follow-builders",
    },
    "bestblogs": {
        "label": "BestBlogs",
        "description": "安装 BestBlogs CLI，用于精选技术阅读（不安装对话式 Agent Skills）。",
        "repo": "https://github.com/ginobefun/bestblogs",
        "install_kind": "npm-cli",
        "command": "bestblogs discover today --limit 20 --json 2>/dev/null",
        "next_steps": [
            "登录（必须）：bestblogs auth login，按提示粘贴在 https://bestblogs.dev/settings 生成的 API Key",
            "可选：bestblogs intake setup（设置兴趣画像）",
        ],
    },
    "ak-rss-digest": {
        "label": "AK RSS Digest",
        "description": "接入 rookie-ricardo/erduo-skills 里的 RSS/Atom 摘要。",
        "repo": "https://github.com/rookie-ricardo/erduo-skills.git",
        "install_kind": "git-subskill",
        "repo_dir": "erduo-skills",
        "link_name": "ak-rss-digest",
    },
}


class ChineseArgumentParser(argparse.ArgumentParser):
    def format_usage(self) -> str:
        return super().format_usage().replace("usage:", "用法：")

    def format_help(self) -> str:
        text = super().format_help()
        replacements = {
            "usage:": "用法：",
            "optional arguments:": "选项：",
            "options:": "选项：",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        return text


def expand_path(value: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(value))).resolve()


def shell_path(path) -> str:
    return shlex.quote(str(path))


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_yaml(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def copy_if_missing(source: Path, target: Path, force: bool = False, dry_run: bool = False) -> bool:
    if target.exists() and not force:
        print(f"[ok] {target.name} 已存在")
        return False
    print(f"[ok] 从 {source.name} 创建 {target.name}")
    if dry_run:
        return True
    shutil.copyfile(source, target)
    return True


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def run_command(cmd: list[str], cwd: Optional[Path] = None, dry_run: bool = False) -> None:
    cwd_text = f" (cwd: {cwd})" if cwd else ""
    print(f"[run] {' '.join(shlex.quote(part) for part in cmd)}{cwd_text}")
    if dry_run:
        return
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def ensure_directory(path: Path, dry_run: bool = False) -> None:
    print(f"[ok] 确保目录存在：{path}")
    if not dry_run:
        path.mkdir(parents=True, exist_ok=True)


def ensure_parent(path: Path, dry_run: bool = False) -> None:
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)


def path_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".ai-news-keji-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


def detect_installed_external_skills(install_dir: Path) -> dict[str, bool]:
    return {name: external_skill_installed(name, install_dir) for name in EXTERNAL_SKILLS}


def external_skill_installed(name: str, install_dir: Path) -> bool:
    install_dir = expand_path(str(install_dir))
    if name == "follow-builders":
        return (install_dir / "follow-builders" / ".git").exists()
    if name == "bestblogs":
        return command_exists("bestblogs")
    if name == "ak-rss-digest":
        repo_path = install_dir / "erduo-skills"
        link_path = install_dir / "ak-rss-digest"
        return (repo_path / ".git").exists() and link_path.exists()
    return False


def clone_or_update(repo: str, path: Path, dry_run: bool = False) -> None:
    if path.exists():
        if (path / ".git").exists():
            run_command(["git", "-C", str(path), "pull", "--ff-only"], dry_run=dry_run)
        else:
            print(f"[warn] {path} 已存在，但不是 git 仓库；跳过 clone")
        return
    run_command(["git", "clone", repo, str(path)], dry_run=dry_run)


def symlink_force(source: Path, target: Path, dry_run: bool = False) -> None:
    print(f"[ok] 建立软链 {target} -> {source}")
    if dry_run:
        return
    ensure_parent(target)
    if target.is_symlink() or target.exists():
        if target.is_dir() and not target.is_symlink():
            print(f"[warn] {target} 已经是目录；保持不变")
            return
        target.unlink()
    target.symlink_to(source, target_is_directory=True)


def install_follow_builders(install_dir: Path, link_targets: list[Path], dry_run: bool = False) -> dict:
    meta = EXTERNAL_SKILLS["follow-builders"]
    install_path = install_dir / meta["clone_dir"]
    scripts_dir = install_path / "scripts"
    link_name = meta["link_name"]
    already_installed = (install_path / ".git").exists()

    if already_installed:
        print(f"[ok] follow-builders 本条已安装：{install_path}，跳过 clone / npm install")
    else:
        clone_or_update(meta["repo"], install_path, dry_run=dry_run)
        if command_exists("npm"):
            run_command(["npm", "install"], cwd=scripts_dir, dry_run=dry_run)
        else:
            print("[warn] 未安装 npm；未安装 follow-builders 依赖")

    link_skill_to_targets(install_path, link_name, link_targets, dry_run=dry_run)

    return {
        "enabled": True,
        "install_kind": meta["install_kind"],
        "repo": meta["repo"],
        "install_path": str(install_path),
        "link_name": link_name,
        "command": f"cd {shell_path(scripts_dir)} && node prepare-digest.js 2>/dev/null",
    }


def bestblogs_logged_in() -> Optional[bool]:
    """返回 True/False/None。None 表示无法判定（命令缺失或调用失败）。"""
    if not command_exists("bestblogs"):
        return None
    try:
        result = subprocess.run(
            ["bestblogs", "auth", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return None
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return None
    return bool(data.get("loggedIn"))


def guide_bestblogs_login(dry_run: bool = False) -> None:
    if dry_run:
        print("[next] 登录（必须）：bestblogs auth login")
        return

    status = bestblogs_logged_in()
    if status is True:
        print("[ok] BestBlogs 已登录（bestblogs auth status 返回 loggedIn=true）")
        return
    if status is None:
        print("[warn] 未能确认 BestBlogs 登录状态；安装完成后请手动运行：bestblogs auth login")
        return

    print("[next] BestBlogs 当前未登录，未登录时 `bestblogs discover` 会返回空数据，日报里这一节将被跳过。")
    print("[next] 请在 https://bestblogs.dev/settings 生成 API Key，然后运行：bestblogs auth login")
    if not prompt_yes_no("现在就交互式登录吗？（会调起 bestblogs auth login）", default=True):
        print("[next] 跳过登录；准备好 API Key 后请手动运行：bestblogs auth login")
        return

    try:
        subprocess.run(["bestblogs", "auth", "login"], check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"[warn] 调起 bestblogs auth login 失败：{exc}；请手动运行该命令")
        return

    after = bestblogs_logged_in()
    if after is True:
        print("[ok] BestBlogs 登录成功")
    elif after is False:
        print("[warn] 登录后 bestblogs auth status 仍显示未登录；请检查 API Key 后重试")
    else:
        print("[warn] 未能确认登录状态，请稍后运行：bestblogs auth status")


def install_bestblogs(dry_run: bool = False) -> dict:
    meta = EXTERNAL_SKILLS["bestblogs"]

    if command_exists("bestblogs"):
        print("[ok] BestBlogs CLI 已安装（检测到 bestblogs 命令），跳过 npm install")
    else:
        if command_exists("npm"):
            run_command(["npm", "install", "-g", "@bestblogs/cli"], dry_run=dry_run)
        else:
            print("[warn] 未安装 npm；未安装 @bestblogs/cli")

    guide_bestblogs_login(dry_run=dry_run)

    return {
        "enabled": True,
        "install_kind": meta["install_kind"],
        "repo": meta["repo"],
        "command": meta["command"],
    }


def install_ak_rss_digest(install_dir: Path, link_targets: list[Path], dry_run: bool = False) -> dict:
    meta = EXTERNAL_SKILLS["ak-rss-digest"]
    repo_path = install_dir / meta["repo_dir"]
    source_path = repo_path / "skills" / "ak-rss-digest"
    install_path = install_dir / "ak-rss-digest"
    link_name = meta["link_name"]

    if (repo_path / ".git").exists() and install_path.exists():
        print(f"[ok] ak-rss-digest 本条已安装：{install_path}，跳过 clone")
    else:
        clone_or_update(meta["repo"], repo_path, dry_run=dry_run)
        symlink_force(source_path, install_path, dry_run=dry_run)
    link_skill_to_targets(install_path, link_name, link_targets, dry_run=dry_run)

    return {
        "enabled": True,
        "install_kind": meta["install_kind"],
        "repo": meta["repo"],
        "install_path": str(install_path),
        "source_path": str(source_path),
        "repo_path": str(repo_path),
        "link_name": link_name,
        "command": f"cd {shell_path(repo_path)} && python3 skills/ak-rss-digest/scripts/fetch_today_feed_items.py --days 1 --timezone Asia/Shanghai --format json 2>/dev/null",
    }


def link_skill_to_targets(source: Path, link_name: str, link_targets: list[Path], dry_run: bool = False) -> None:
    for target_dir in link_targets:
        ensure_directory(target_dir, dry_run=dry_run)
        symlink_force(source, target_dir / link_name, dry_run=dry_run)


def install_external_skill(name: str, install_dir: Path, link_targets: list[Path], dry_run: bool = False) -> dict:
    if name == "follow-builders":
        return install_follow_builders(install_dir, link_targets, dry_run=dry_run)
    if name == "bestblogs":
        return install_bestblogs(dry_run=dry_run)
    if name == "ak-rss-digest":
        return install_ak_rss_digest(install_dir, link_targets, dry_run=dry_run)
    raise ValueError(f"Unknown external skill: {name}")


def parse_skill_list(value: Optional[str]) -> list[str]:
    if not value:
        return []
    names = [item.strip() for item in value.split(",") if item.strip()]
    unknown = [name for name in names if name not in EXTERNAL_SKILLS]
    if unknown:
        raise SystemExit(f"未知外部 skill：{', '.join(unknown)}")
    return names


def parse_answer_skill_list(value) -> list[str]:
    if value in (None, False):
        return []
    if value is True:
        return list(EXTERNAL_SKILLS)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "none", "no", "false", "skip", "later"}:
            return []
        if normalized in {"all", "yes", "true", "recommended"}:
            return list(EXTERNAL_SKILLS)
        return parse_skill_list(value)
    if isinstance(value, list):
        names = [str(item).strip() for item in value if str(item).strip()]
        unknown = [name for name in names if name not in EXTERNAL_SKILLS]
        if unknown:
            raise SystemExit(f"未知外部 skill：{', '.join(unknown)}")
        return names
    raise SystemExit("answers-file 里的 external_skills 必须是数组、字符串或布尔值")


def load_answers_file(path: str) -> dict:
    answers_path = expand_path(path)
    try:
        with answers_path.open(encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"找不到 answers-file：{answers_path}") from None
    except json.JSONDecodeError as exc:
        raise SystemExit(f"answers-file 不是合法 JSON：{exc}") from None
    if not isinstance(data, dict):
        raise SystemExit("answers-file 顶层必须是 JSON object")
    return data


def choose_external_skills(args, guided_setup: bool = False) -> list[str]:
    explicit = parse_skill_list(args.skills)
    if explicit:
        return explicit
    if args.install_external_skills:
        return list(EXTERNAL_SKILLS)
    if args.yes:
        return []

    selected = []
    install_dir = expand_path(args.install_dir)
    print("\n可选外部集成：")
    if guided_setup:
        print("建议安装：这些集成可以扩大 AI、builder、博客和 RSS 来源覆盖。")
    for name, meta in EXTERNAL_SKILLS.items():
        if external_skill_installed(name, install_dir):
            print(f"- {meta['label']}：本条已安装，自动加入并跳过提问")
            selected.append(name)
            continue
        if prompt_yes_no(f"是否安装并启用 {meta['label']}？{meta['description']}", default=guided_setup):
            selected.append(name)
    return selected


def choose_link_targets(args, selected: list[str]) -> list[Path]:
    raw_targets: list[str] = []

    if args.skill_dir:
        print("[warn] --skill-dir 已弃用；请改用 --link-target")
        raw_targets.append(args.skill_dir)

    if args.link_target:
        raw_targets.extend(args.link_target)

    if args.no_link:
        raw_targets = []

    if not raw_targets and selected:
        if args.yes or args.install_external_skills or args.skills or args.answers_file:
            raw_targets = DEFAULT_LINK_TARGETS[:]
        else:
            if prompt_yes_no("是否通过软链把外部 skills 注册到 ~/.claude/skills？", default=True):
                raw_targets.append("~/.claude/skills")
            if prompt_yes_no("是否也通过软链注册到 ~/.codex/skills？", default=False):
                raw_targets.append("~/.codex/skills")

    return [expand_path(target) for target in raw_targets]


def create_local_configs(force: bool = False, dry_run: bool = False) -> None:
    copy_if_missing(SKILL_ROOT / "config.example.yaml", SKILL_ROOT / "config.yaml", force=force, dry_run=dry_run)
    copy_if_missing(SKILL_ROOT / "sources.example.yaml", SKILL_ROOT / "sources.yaml", force=force, dry_run=dry_run)


def update_pipeline(config: dict, selected: list[str]) -> None:
    if selected:
        add_enabled_source(config, "external_skills")


def update_setup_state(config: dict, selected: list[str], guided_setup_completed: bool = False) -> None:
    setup = config.setdefault("setup", {})
    setup["initialized"] = True
    setup["init_schema_version"] = SETUP_SCHEMA_VERSION
    setup["initialized_at"] = datetime.now(timezone.utc).isoformat()
    if selected or "selected_external_skills" not in setup:
        setup["selected_external_skills"] = selected
    if guided_setup_completed:
        setup["guided_setup_completed"] = True
    else:
        setup.setdefault("guided_setup_completed", False)
    setup_steps(config)


def configure_external_skills(config: dict, selected: list[str], install_dir: Path, link_targets: list[Path], dry_run: bool = False) -> None:
    external_config = config.setdefault("external_skills", {})
    external_config["install_dir"] = str(install_dir)
    external_config["link_targets"] = [str(path) for path in link_targets]

    for name in selected:
        print(f"\n正在安装 {name}...")
        external_config[name] = install_external_skill(name, install_dir, link_targets, dry_run=dry_run)


def create_runtime_dirs(config: dict, dry_run: bool = False) -> None:
    paths = config.get("paths", {})
    for key in ("output_dir", "cache_dir"):
        raw = paths.get(key)
        if raw:
            ensure_directory(expand_path(str(raw)), dry_run=dry_run)


def check_config() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []
    first_time_setup = False
    needs_agent_setup = False
    config_path = SKILL_ROOT / "config.yaml"
    sources_path = SKILL_ROOT / "sources.yaml"

    if not config_path.exists():
        first_time_setup = True
        errors.append("缺少 config.yaml，需要先完成 Agent 初始化向导")
        add_init_recommendations(recommendations, first_time=True)
        return print_check_result(errors, warnings, recommendations, first_time_setup=first_time_setup)
    if not sources_path.exists():
        first_time_setup = True
        needs_agent_setup = True
        errors.append("缺少 sources.yaml，需要先完成 Agent 初始化向导")
        add_init_recommendations(recommendations, first_time=True)
        return print_check_result(errors, warnings, recommendations, first_time_setup=first_time_setup)

    config = load_yaml(config_path)
    setup = config.get("setup") or {}
    if setup.get("initialized") is not True:
        first_time_setup = True
        needs_agent_setup = True
        errors.append("setup.initialized 不是 true，需要先完成 Agent 初始化向导")
        add_init_recommendations(recommendations, first_time=True)
    elif setup.get("guided_setup_completed") is not True:
        needs_agent_setup = True
        errors.append("尚未完成初始化向导，需要在 Agent 对话中确认集成、Newsletter、输出目录和个人偏好")
        recommendations.append("继续 Agent 分步初始化：按当前步骤说明作用并等待用户回答")
    elif setup.get("guided_setup_completed") is True:
        incomplete_steps = [step for step, done in setup_steps(config).items() if not done]
        if incomplete_steps:
            needs_agent_setup = True
            errors.append(f"初始化向导仍有未完成步骤：{', '.join(incomplete_steps)}")
            recommendations.append("继续 Agent 分步初始化：按当前步骤说明作用并等待用户回答")
    if int(setup.get("init_schema_version") or 0) < SETUP_SCHEMA_VERSION:
        needs_agent_setup = True
        errors.append("setup.init_schema_version 已过期，需要重新完成 Agent 初始化向导或手动迁移 config.yaml")
        add_init_recommendations(recommendations)
    if needs_agent_setup:
        return print_check_result(errors, warnings, recommendations, first_time_setup=first_time_setup)

    paths = config.get("paths") or {}
    for key in ("output_dir", "cache_dir"):
        raw = paths.get(key)
        if not raw:
            errors.append(f"缺少 paths.{key}")
            add_init_recommendations(recommendations)
            continue
        path = expand_path(str(raw))
        if not path.exists():
            errors.append(f"paths.{key} 不存在：{path}")
            add_init_recommendations(recommendations)
        elif not path_writable(path):
            errors.append(f"paths.{key} 不可写：{path}")

    pipeline = config.get("pipeline") or {}
    enabled_sources = pipeline.get("enabled_sources") or []
    if not enabled_sources:
        errors.append("pipeline.enabled_sources 为空")

    check_email(errors, warnings, config, enabled_sources)
    check_external(errors, warnings, recommendations, config, enabled_sources)

    return print_check_result(errors, warnings, recommendations, first_time_setup=first_time_setup)


def check_email(errors: list[str], warnings: list[str], config: dict, enabled_sources: list[str]) -> None:
    if "email" not in enabled_sources:
        return

    pipeline = config.get("pipeline") or {}
    skip_unavailable = bool(pipeline.get("skip_unavailable_sources"))
    email_config = config.get("email") or {}
    mode = email_config.get("mode", "none")

    def report_email_problem(message: str) -> None:
        if skip_unavailable:
            warnings.append(f"{message}；因为 pipeline.skip_unavailable_sources 为 true，将跳过该来源")
        else:
            errors.append(message)

    if mode == "none":
        report_email_problem("已启用 email 来源，但 email.mode 为 none")
        return
    if mode == "mcp":
        warnings.append("email.mode 为 mcp；请确认当前 Agent 运行环境提供 email/Gmail MCP 工具")
        return
    if mode != "imap":
        report_email_problem(f"不支持的 email.mode：{mode}")
        return

    imap_config = email_config.get("imap") or {}
    if not imap_config.get("host"):
        report_email_problem("缺少 email.imap.host")

    username_env = imap_config.get("username_env") or "AI_NEWS_IMAP_USERNAME"
    password_env = imap_config.get("password_env") or "AI_NEWS_IMAP_PASSWORD"
    if not os.environ.get(username_env):
        report_email_problem(f"缺少 IMAP 账号环境变量：{username_env}")
    if not os.environ.get(password_env):
        report_email_problem(f"缺少 IMAP 密码/授权码环境变量：{password_env}")


def check_external(errors: list[str], warnings: list[str], recommendations: list[str], config: dict, enabled_sources: list[str]) -> None:
    if "external_skills" not in enabled_sources:
        return

    pipeline = config.get("pipeline") or {}
    skip_unavailable = bool(pipeline.get("skip_unavailable_sources"))
    external_config = config.get("external_skills") or {}
    enabled_items = {
        name: item
        for name, item in external_config.items()
        if isinstance(item, dict) and item.get("enabled")
    }
    if not enabled_items:
        message = "已启用 external_skills 来源，但没有启用任何外部 skill 条目"
        if skip_unavailable:
            warnings.append(f"{message}；因为 pipeline.skip_unavailable_sources 为 true，将跳过该来源组")
        else:
            errors.append(message)
        recommendations.append("在 config.yaml 里关闭 external_skills，或运行：python3 scripts/init.py --skills follow-builders,bestblogs,ak-rss-digest")
        return

    def report_external_problem(message: str, recommendation: str) -> None:
        if skip_unavailable:
            warnings.append(f"{message}；因为 pipeline.skip_unavailable_sources 为 true，将跳过该来源")
        else:
            errors.append(message)
        recommendations.append(recommendation)

    install_dir = external_config.get("install_dir")
    if install_dir and not expand_path(str(install_dir)).exists():
        warnings.append(f"external_skills.install_dir 尚不存在：{expand_path(str(install_dir))}")

    for name, item in enabled_items.items():
        command = item.get("command")
        if not command:
            report_external_problem(
                f"外部 skill {name} 已启用，但缺少 command",
                f"重新配置 {name}：python3 scripts/init.py --skills {name}",
            )

        if name == "bestblogs":
            if not command_exists("bestblogs"):
                report_external_problem(
                    "bestblogs 已启用，但找不到 bestblogs 命令",
                    "安装 BestBlogs CLI：python3 scripts/init.py --skills bestblogs",
                )
            else:
                login_status = bestblogs_logged_in()
                if login_status is False:
                    report_external_problem(
                        "bestblogs 已启用，但 BestBlogs CLI 未登录；未登录时 discover 接口返回空数据",
                        "登录 BestBlogs：bestblogs auth login（API Key 在 https://bestblogs.dev/settings 生成）",
                    )
                elif login_status is None:
                    warnings.append("无法确认 BestBlogs 登录状态；如果日报里 BestBlogs 一直为空，请运行 bestblogs auth status 排查")
            continue

        install_path = item.get("install_path")
        if not install_path:
            report_external_problem(
                f"外部 skill {name} 已启用，但缺少 install_path",
                f"安装 {name}：python3 scripts/init.py --skills {name}",
            )
            continue
        if not expand_path(str(install_path)).exists():
            report_external_problem(
                f"外部 skill {name} 的 install_path 不存在：{expand_path(str(install_path))}",
                f"安装 {name}：python3 scripts/init.py --skills {name}",
            )


def add_init_recommendations(recommendations: list[str], first_time: bool = False) -> None:
    if first_time:
        recommendations.append("进入 Agent 分步初始化：下一条消息只推进第 1 步外部集成选择")
        return
    recommendations.append("继续 Agent 分步初始化：按当前步骤说明作用并等待用户回答")


def unique_items(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def print_check_result(
    errors: list[str],
    warnings: list[str],
    recommendations: list[str],
    first_time_setup: bool = False,
) -> int:
    should_print_agent_flow = first_time_setup or any("Agent 分步初始化" in item for item in recommendations)
    if first_time_setup and errors:
        print("[info] 检测到首次启动：本地初始化尚未完成")
        print("[info] 进入 Agent 初始化向导：在对话中收集配置，再写入本地文件")
    for warning in warnings:
        print(f"[warn] {warning}")
    for error in errors:
        print(f"[error] {error}")
    if errors:
        print("[error] 初始化检查失败")
        for recommendation in unique_items(recommendations) or ["进入 Agent 初始化向导"]:
            print(f"[next] {recommendation}")
        if should_print_agent_flow:
            print()
            print_agent_setup_flow(
                SKILL_ROOT,
                installed=detect_installed_external_skills(expand_path(DEFAULT_INSTALL_DIR)),
            )
        return 1
    for recommendation in unique_items(recommendations):
        print(f"[next] 可选：{recommendation}")
    print("[ok] 初始化检查通过")
    return 0


def run_reconfigure(args, answers: Optional[dict], installed_status: dict[str, bool]) -> int:
    section = args.reconfigure
    config_path = SKILL_ROOT / "config.yaml"

    if answers is None:
        if not config_path.exists():
            print("[error] config.yaml 不存在；请先完成首次初始化，再使用 --reconfigure")
            return 1
        print_reconfigure_flow(section, SKILL_ROOT, installed=installed_status)
        return 1

    if not config_path.exists():
        print("[error] config.yaml 不存在；--reconfigure 需要在已初始化的项目里执行")
        return 1

    config = load_yaml(config_path)
    install_dir = expand_path(args.install_dir)

    if section == "external_skills":
        selected = parse_answer_skill_list(answers.get("external_skills"))
        link_targets = choose_link_targets(args, selected)
        if selected:
            ensure_directory(install_dir, dry_run=args.dry_run)
            configure_external_skills(config, selected, install_dir, link_targets, dry_run=args.dry_run)
            update_pipeline(config, selected)
        else:
            remove_enabled_source(config, "external_skills")
            print("[ok] 已关闭外部 skills 来源；现有 external_skills.* 条目保留，可手动删除")
        config.setdefault("setup", {})["selected_external_skills"] = selected
        mark_setup_step(config, "external_skills_prompted")
    elif section == "newsletter":
        apply_newsletter_answer(config, answers.get("newsletter", "later"))
    elif section == "output_dir":
        apply_output_dir_answer(config, answers.get("output_dir"))
        create_runtime_dirs(config, dry_run=args.dry_run)
    elif section == "preferences":
        apply_preferences_answer(config, SKILL_ROOT, answers.get("preferences", ""), dry_run=args.dry_run)

    if args.dry_run:
        print(f"[ok] dry run 完成；未更新 config.yaml（section={section}）")
        return 0

    write_yaml(config_path, config)
    print(f"[ok] 已更新 config.yaml（section={section}）")
    print("[next] 请运行：python3 scripts/init.py --check")
    return 0


def main() -> int:
    parser = ChineseArgumentParser(
        description="初始化 ai-news-keji 本地配置和可选外部集成",
        add_help=False,
    )
    parser.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    parser.add_argument("--check", action="store_true", help="检查初始化是否完成，已启用来源是否可用")
    parser.add_argument("--yes", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--force", action="store_true", help="用示例模板覆盖 config.yaml 和 sources.yaml")
    parser.add_argument("--dry-run", action="store_true", help="只打印将执行的动作，不修改文件或安装依赖")
    parser.add_argument("--answers-file", default=None, help="使用对话式初始化收集到的 JSON 答案完成初始化")
    parser.add_argument("--install-dir", default=DEFAULT_INSTALL_DIR, help="外部 skill 源码的受管理安装目录")
    parser.add_argument("--link-target", action="append", default=None, help="接收软链的 skill 目录；可重复传入")
    parser.add_argument("--no-link", action="store_true", help="只安装外部 skill 源码，不软链到 agent skill 目录")
    parser.add_argument("--skill-dir", default=None, help="已弃用；请改用 --link-target")
    parser.add_argument("--install-external-skills", action="store_true", help="安装并启用所有可选外部 skills")
    parser.add_argument("--skills", default=None, help="要安装的外部 skills，逗号分隔：follow-builders,bestblogs,ak-rss-digest")
    parser.add_argument(
        "--reconfigure",
        choices=RECONFIGURE_SECTIONS,
        default=None,
        help="只重新配置某一步：external_skills / newsletter / output_dir / preferences",
    )
    args = parser.parse_args()

    if args.check:
        return check_config()

    answers = load_answers_file(args.answers_file) if args.answers_file else None
    installed_status = detect_installed_external_skills(expand_path(args.install_dir))

    if args.reconfigure:
        return run_reconfigure(args, answers, installed_status)
    if args.yes and not (args.install_external_skills or args.skills or args.answers_file):
        print_agent_setup_flow(SKILL_ROOT, installed=installed_status)
        return 1

    should_show_agent_flow = not (args.answers_file or args.install_external_skills or args.skills)
    if should_show_agent_flow:
        print_agent_setup_flow(SKILL_ROOT, installed=installed_status)
        return 1

    guided_setup = False
    config_path = SKILL_ROOT / "config.yaml"
    sources_path = SKILL_ROOT / "sources.yaml"
    existing_config = config_path.exists()
    existing_sources = sources_path.exists()

    print(f"ai-news-keji init: {SKILL_ROOT}")
    if not existing_config or not existing_sources:
        print("[info] 检测到首次启动；正在创建本地配置文件和运行目录")

    if not command_exists("git"):
        print("[warn] 未安装 git；无法安装基于 git 的外部 skills")

    create_local_configs(force=args.force, dry_run=args.dry_run)
    config = load_yaml(config_path if config_path.exists() else SKILL_ROOT / "config.example.yaml")
    if existing_config and (config.get("setup") or {}).get("initialized") is not True:
        print("[info] 本地初始化状态不完整；正在补齐初始化状态")
    if answers is not None:
        selected = parse_answer_skill_list(answers.get("external_skills"))
    else:
        selected = choose_external_skills(args, guided_setup=guided_setup)
    install_dir = expand_path(args.install_dir)
    link_targets = choose_link_targets(args, selected)

    if selected:
        ensure_directory(install_dir, dry_run=args.dry_run)
        configure_external_skills(config, selected, install_dir, link_targets, dry_run=args.dry_run)
        update_pipeline(config, selected)
    else:
        external_config = config.setdefault("external_skills", {})
        external_config.setdefault("install_dir", str(install_dir))
        external_config.setdefault("link_targets", [str(path) for path in link_targets])
        print("[ok] 未选择可选外部 skills")

    if answers is not None:
        apply_guided_answers(config, SKILL_ROOT, answers, dry_run=args.dry_run)
        guided_setup_completed = True
    else:
        guided_setup_completed = False

    update_setup_state(config, selected, guided_setup_completed=guided_setup_completed)
    create_runtime_dirs(config, dry_run=args.dry_run)

    if args.dry_run:
        print("[ok] dry run 完成；未更新 config.yaml")
        return 0

    write_yaml(config_path, config)
    print("[ok] 已写入 config.yaml")
    print("[next] 请运行：python3 scripts/init.py --check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
