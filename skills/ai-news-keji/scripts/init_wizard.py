"""
ai-news-keji 首次启动 Agent 对话式向导。

用户引导流程集中放在这里，让 scripts/init.py 专注于配置校验、
可选安装命令和 CLI 入口。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


SETUP_STEPS = (
    "external_skills_prompted",
    "newsletter_prompted",
    "output_dir_selected",
    "preferences_prompted",
)

INPUT_EOF_SEEN = False

NEWSLETTER_SUBSCRIBE_URLS = {
    "TLDR AI": "https://tldr.tech/ai",
    "TLDR Dev": "https://tldr.tech/webdev",
    "TLDR Founders": "https://tldr.tech/founders",
    "TLDR": "https://tldr.tech",
    "The Rundown AI": "https://www.rundown.ai",
    "The Neuron": "https://www.theneurondaily.com/subscribe",
    "AI Breakfast": "https://aibreakfast.ai",
    "AI Valley": "https://www.theaivalley.com/subscribe",
    "Ben's Bites": "https://bensbites.co",
    "Latent.Space": "https://www.latent.space",
    "DeepLearning.AI": "https://www.deeplearning.ai/thebatch",
}

IMAP_HOST_HINTS = (
    "Gmail / Google Workspace：imap.gmail.com，端口 993，开启 SSL；如开启两步验证，请使用 App Password。",
    "iCloud Mail：imap.mail.me.com，端口 993，开启 SSL；请使用 app-specific password。",
    "Outlook / Microsoft 365：outlook.office365.com，端口 993，开启 SSL。",
    "QQ 邮箱：imap.qq.com，端口 993，开启 SSL；请使用授权码。",
    "网易 163 邮箱：imap.163.com，端口 993，开启 SSL；请使用授权码。",
)


def input_was_unavailable() -> bool:
    return INPUT_EOF_SEEN


def expand_path(value: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(value))).resolve()


def ensure_parent(path: Path, dry_run: bool = False) -> None:
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def prompt_yes_no(question: str, default: bool = False) -> bool:
    global INPUT_EOF_SEEN
    suffix = "默认：是" if default else "默认：否"
    try:
        answer = input(f"{question} [{suffix}] ").strip().lower()
    except EOFError:
        INPUT_EOF_SEEN = True
        print("[warn] 当前环境无法接收交互式输入，使用安全默认值：否")
        return False
    if not answer:
        return default
    return answer in {"y", "yes", "是", "好"}


def prompt_text(question: str, default: str = "") -> str:
    global INPUT_EOF_SEEN
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{question}{suffix} ").strip()
    except EOFError:
        INPUT_EOF_SEEN = True
        print("[warn] 当前环境无法接收交互式输入，使用默认值")
        return default
    return answer or default


def prompt_choice(question: str, choices: list[str], default: str) -> str:
    global INPUT_EOF_SEEN
    choice_text = "/".join(choices)
    while True:
        try:
            answer = input(f"{question} ({choice_text}) [{default}] ").strip().lower()
        except EOFError:
            INPUT_EOF_SEEN = True
            print("[warn] 当前环境无法接收交互式输入，使用默认值")
            return default
        if not answer:
            return default
        if answer in choices:
            return answer
        print(f"[warn] 请输入其中一个选项：{choice_text}")


def prompt_multiline(question: str) -> str:
    global INPUT_EOF_SEEN
    print(question)
    print("可以输入一行或多行。输入空行结束；如果直接回车，则使用默认筛选逻辑。")
    lines: list[str] = []
    while True:
        prefix = "> " if not lines else "... "
        try:
            line = input(prefix).rstrip()
        except EOFError:
            INPUT_EOF_SEEN = True
            if not lines:
                print("[warn] 当前环境无法接收交互式输入，使用默认筛选逻辑")
            break
        if not line:
            break
        lines.append(line)
    return "\n".join(lines).strip()


def setup_steps(config: dict[str, Any]) -> dict[str, bool]:
    setup = config.setdefault("setup", {})
    steps = setup.setdefault("steps", {})
    for step in SETUP_STEPS:
        steps.setdefault(step, False)
    return steps


def mark_setup_step(config: dict[str, Any], step: str, value: bool = True) -> None:
    setup_steps(config)[step] = value


def add_enabled_source(config: dict[str, Any], source: str) -> None:
    pipeline = config.setdefault("pipeline", {})
    enabled_sources = pipeline.setdefault("enabled_sources", ["rss", "websites"])
    if source not in enabled_sources:
        enabled_sources.append(source)


def remove_enabled_source(config: dict[str, Any], source: str) -> None:
    pipeline = config.setdefault("pipeline", {})
    enabled_sources = pipeline.setdefault("enabled_sources", [])
    pipeline["enabled_sources"] = [item for item in enabled_sources if item != source]


def load_newsletter_sources(skill_root: Path) -> list[dict[str, Any]]:
    local_sources = skill_root / "sources.yaml"
    example_sources = skill_root / "sources.example.yaml"
    source_path = local_sources if local_sources.exists() else example_sources
    if not source_path.exists():
        return []
    data = load_yaml(source_path)
    return [item for item in data.get("email", []) if isinstance(item, dict)]


def newsletter_subscribe_url(item: dict[str, Any]) -> str:
    if item.get("subscribe_url"):
        return str(item["subscribe_url"])
    return NEWSLETTER_SUBSCRIBE_URLS.get(str(item.get("name") or ""), "")


def print_newsletter_subscription_guide(skill_root: Path) -> None:
    items = load_newsletter_sources(skill_root)
    if not items:
        print("[warn] 未在 sources.yaml 或 sources.example.yaml 中找到 Newsletter 来源")
        return

    print("\nNewsletter 来源覆盖：")
    print("请先订阅你希望日报读取的 Newsletter。下方发件人地址会作为邮箱白名单。")
    for item in items:
        name = str(item.get("name") or "未命名")
        category = str(item.get("category") or "未分类")
        frequency = str(item.get("frequency") or "未知频率")
        sender = str(item.get("from") or "未知发件人")
        url = newsletter_subscribe_url(item)
        link = f" | {url}" if url else ""
        print(f"- {name}（{category}，{frequency}）| 发件人：{sender}{link}")


def print_imap_setup_guide() -> None:
    print("\nIMAP 设置：")
    print("1. 先在邮箱设置里开启 IMAP。")
    print("2. 如果邮箱服务商要求，请使用 App Password / 授权码，不要使用明文登录密码。")
    print("3. 邮箱账号和密码只放进环境变量，不写入 config.yaml。")
    for hint in IMAP_HOST_HINTS:
        print(f"- {hint}")


EXTERNAL_SKILL_LABELS = {
    "follow-builders": "follow-builders",
    "bestblogs": "BestBlogs",
    "ak-rss-digest": "ak-rss-digest",
}


def print_step_external_skills(installed: dict[str, bool] | None = None, heading: str = "第 1 步") -> None:
    installed = installed or {}
    pending = [label for key, label in EXTERNAL_SKILL_LABELS.items() if not installed.get(key)]
    print(f"\n{heading}：必须调用 AskUserQuestion 工具")
    print("  question: 选择要接入的外部集成（可多选）")
    print("  multiSelect: true")
    print("  说明：这一步决定是否接入额外信息源，用来扩大 AI builder、技术博客和 RSS 覆盖。")
    if pending:
        print(f"  推荐：{('、'.join(pending))} 尚未安装，建议勾选。")
    else:
        print("  推荐：三个集成均已安装，本步会自动复用现有安装。")
    print("  options（已安装的项 label 必须带“（本条已安装）”后缀）：")
    for key, label in EXTERNAL_SKILL_LABELS.items():
        suffix = "（本条已安装）" if installed.get(key) else ""
        print(f"  - {label}{suffix}")
    print("  - 暂不安装")


def print_step_newsletter(heading: str = "第 2 步") -> None:
    print(f"\n{heading}：必须调用 AskUserQuestion 工具")
    print("  question: 是否接入邮件 Newsletter 来源？")
    print("  multiSelect: false")
    print("  options:")
    print("  - imap（现在配置 IMAP 接入；适合任意标准邮箱）")
    print("  - mcp（使用当前 Agent runtime 已注册的 Gmail / 邮件 MCP server）")
    print("  - later（先跳过，稍后再配）")
    print("  - no（不接入邮件来源）")
    print("  说明前先读取 sources.yaml 或 sources.example.yaml，列出 Newsletter 名称、发件人和订阅链接。")
    print("  IMAP vs MCP 简介：IMAP 兼容所有邮箱、可独立烟测；MCP 走 OAuth、由 runtime 管理凭据，但目前主要面向 Gmail 且需要预先在 Agent 环境配好 MCP server。")


def print_step_imap(heading: str = "第 2.1 步（仅当上一步选 imap 时）") -> None:
    print(f"\n{heading}：调用一次 AskUserQuestion，包含 4 个子问题")
    print("  - IMAP host：默认 imap.gmail.com，预设 imap.qq.com / imap.163.com / outlook.office365.com，其他可自定义")
    print("  - IMAP folder：默认 INBOX")
    print("  - 账号环境变量名：默认 AI_NEWS_IMAP_USERNAME")
    print("  - 密码/授权码环境变量名：默认 AI_NEWS_IMAP_PASSWORD")
    print("  说明：账号和密码只通过环境变量提供，不写入 config.yaml。")


def print_step_output_dir(heading: str = "第 3 步") -> None:
    print(f"\n{heading}：必须调用 AskUserQuestion 工具")
    print("  question: 日报 Markdown 写入哪个目录？")
    print("  options:")
    print("  - ~/ai-news-keji/output（默认）")
    print("  - ~/Documents/ai-news-keji")
    print("  其他路径请用 “其他” 填写。")


def print_step_preferences(heading: str = "第 4 步") -> None:
    print(f"\n{heading}：必须调用 AskUserQuestion 工具")
    print("  question: 选择一个起始画像，或用“其他”输入完整偏好描述")
    print("  options:")
    print("  - 工程 + AI 产品方向")
    print("  - 研究 + 论文方向")
    print("  - 创业 + 投资方向")
    print("  - 暂不填写，使用默认")
    print("  说明：这一步会影响评分、排序和摘要重点。")


def print_agent_setup_flow(skill_root: Path, installed: dict[str, bool] | None = None) -> None:
    print("[info] 进入 ai-news-keji Agent 分步初始化")
    print("[info] 给用户的下一条消息只推进第 1 步；用户回答后再进入下一步。")
    print("[info] 每一步都必须用 AskUserQuestion 工具弹选项卡，不要用普通对话让用户手敲答案。")
    print("\n建议开场（普通文字消息）：")
    print("检测到 ai-news-keji 还没有完成初始化。我会一步步带你完成配置：先选择外部集成，然后设置 Newsletter/IMAP，接着确认输出目录，最后填写个人偏好。下面进入第 1 步。")
    print_step_external_skills(installed)
    print_step_newsletter()
    print_step_imap()
    print_step_output_dir()
    print_step_preferences()
    print("\n全部答案收集完成后，Agent 保存 JSON 并运行：")
    print("python3 scripts/init.py --answers-file /path/to/ai-news-keji-init-answers.json")
    print("内部 JSON 字段：external_skills、newsletter、output_dir、preferences。")


def print_reconfigure_flow(section: str, skill_root: Path, installed: dict[str, bool] | None = None) -> None:
    print(f"[info] 进入 ai-news-keji 单步重配置：{section}")
    print("[info] 必须用 AskUserQuestion 工具弹选项卡收集答案，不要让用户手敲答案。")
    if section == "external_skills":
        print_step_external_skills(installed, heading="重配置：外部集成")
    elif section == "newsletter":
        print_step_newsletter(heading="重配置：Newsletter 来源")
        print_step_imap(heading="如果选择 imap，紧接着在同一轮里调用第二次 AskUserQuestion 收集 IMAP 字段")
    elif section == "output_dir":
        print_step_output_dir(heading="重配置：输出目录")
    elif section == "preferences":
        print_step_preferences(heading="重配置：个人偏好")
    print("\n收集到答案后，Agent 保存 JSON 并运行：")
    print(f"python3 scripts/init.py --answers-file /path/to/answers.json --reconfigure {section}")
    print(f"JSON 只需包含本次重配置的字段（{section}）；其他字段会保持现有 config.yaml 不变。")


def configure_newsletter(config: dict[str, Any], skill_root: Path) -> None:
    print("\nNewsletter 来源：")
    print_newsletter_subscription_guide(skill_root)
    print_imap_setup_guide()

    choice = prompt_choice("现在接入 Newsletter 来源吗？", ["imap", "mcp", "later", "no"], default="later")
    email_config = config.setdefault("email", {})
    imap_config = email_config.setdefault("imap", {})

    setup = config.setdefault("setup", {})
    setup["newsletter_choice"] = choice
    mark_setup_step(config, "newsletter_prompted")

    if choice == "imap":
        add_enabled_source(config, "email")
        email_config["mode"] = "imap"
        imap_config["host"] = prompt_text("IMAP 服务器地址", str(imap_config.get("host") or "imap.gmail.com"))
        imap_config["folder"] = prompt_text("IMAP 邮箱文件夹", str(imap_config.get("folder") or "INBOX"))
        imap_config["username_env"] = prompt_text("邮箱账号环境变量名", str(imap_config.get("username_env") or "AI_NEWS_IMAP_USERNAME"))
        imap_config["password_env"] = prompt_text("邮箱密码/授权码环境变量名", str(imap_config.get("password_env") or "AI_NEWS_IMAP_PASSWORD"))
        print(f"[next] 抓取 Newsletter 前，请先设置环境变量 {imap_config['username_env']} 和 {imap_config['password_env']}")
        print("[next] 烟测命令：python3 scripts/fetch-email-imap.py --date YYYY-MM-DD --config config.yaml --sources sources.yaml")
        return

    if choice == "mcp":
        add_enabled_source(config, "email")
        email_config["mode"] = "mcp"
        print("[next] 请确认当前 Agent runtime（Claude Code / Codex 等）已注册 Gmail 或邮件 MCP server，且具备搜索 + 读取邮件正文的权限。")
        print("[next] MCP 模式下没有独立烟测脚本；首次跑日报时由 Agent 直接调用 MCP 工具按发件人 + 日期检索 Newsletter。")
        return

    email_config["mode"] = "none"
    remove_enabled_source(config, "email")
    if choice == "later":
        print("[next] 已暂缓 Newsletter 接入；准备好后可重新运行 python3 scripts/init.py，或手动编辑 config.yaml")
    else:
        print("[ok] 已关闭 Newsletter 来源")


def configure_output_dir(config: dict[str, Any]) -> None:
    print("\n输出目录：")
    paths = config.setdefault("paths", {})
    current = str(paths.get("output_dir") or "~/ai-news-keji/output")
    output_dir = prompt_text("生成 Markdown 日报的默认目录", current)
    paths["output_dir"] = output_dir
    mark_setup_step(config, "output_dir_selected")


def write_preferences_file(
    config: dict[str, Any],
    skill_root: Path,
    preferences: str,
    dry_run: bool = False,
    overwrite: bool = False,
) -> bool:
    paths = config.setdefault("paths", {})
    raw_path = str(paths.get("filter_rules") or "~/ai-news-keji/filter-rules.md")
    paths["filter_rules"] = raw_path
    filter_path = expand_path(raw_path)

    if filter_path.exists() and not overwrite and not prompt_yes_no(f"{filter_path} 已存在。是否用新的偏好覆盖它？", default=False):
        print("[ok] 已保留现有筛选规则文件")
        return False

    example_path = skill_root / "references" / "filter-rules.example.md"
    default_rules = example_path.read_text(encoding="utf-8") if example_path.exists() else ""
    content = "\n".join(
        [
            "# News Filtering Rules",
            "",
            "这些本地筛选规则由 ai-news-keji 初始化向导创建。",
            "",
            "## 个人偏好",
            "",
            preferences,
            "",
            "## 默认基线规则",
            "",
            default_rules,
        ]
    ).rstrip() + "\n"

    print(f"[ok] 写入偏好筛选规则：{filter_path}")
    if dry_run:
        return True
    ensure_parent(filter_path)
    filter_path.write_text(content, encoding="utf-8")
    return True


def configure_preferences(config: dict[str, Any], skill_root: Path, dry_run: bool = False) -> None:
    print("\n个人筛选偏好：")
    print("建议填写：这样日报会按你的兴趣排序，而不是按泛泛的新闻价值排序。")
    preferences = prompt_multiline(
        "你希望这份日报重点关注什么？可以写主题、角色、项目、内容形式，以及要避开的内容。"
    )
    setup = config.setdefault("setup", {})
    mark_setup_step(config, "preferences_prompted")

    if preferences:
        setup["preferences_configured"] = write_preferences_file(config, skill_root, preferences, dry_run=dry_run)
        return

    setup["preferences_configured"] = False
    print("[ok] 暂时使用内置默认筛选逻辑；之后可提供个人 filter_rules 文件")


def run_guided_setup(config: dict[str, Any], skill_root: Path, dry_run: bool = False) -> bool:
    configure_newsletter(config, skill_root)
    configure_output_dir(config)
    configure_preferences(config, skill_root, dry_run=dry_run)
    return not input_was_unavailable()


def apply_newsletter_answer(config: dict[str, Any], answer: Any) -> None:
    if isinstance(answer, str):
        answer = {"choice": answer}
    if not isinstance(answer, dict):
        answer = {}

    choice = str(answer.get("choice") or answer.get("mode") or "later").strip().lower()
    if choice not in {"imap", "mcp", "later", "no"}:
        raise ValueError("newsletter.choice 必须是 imap、mcp、later 或 no")

    email_config = config.setdefault("email", {})
    imap_config = email_config.setdefault("imap", {})
    setup = config.setdefault("setup", {})
    setup["newsletter_choice"] = choice
    mark_setup_step(config, "newsletter_prompted")

    if choice == "imap":
        add_enabled_source(config, "email")
        email_config["mode"] = "imap"
        imap_config["host"] = str(answer.get("host") or imap_config.get("host") or "imap.gmail.com")
        imap_config["folder"] = str(answer.get("folder") or imap_config.get("folder") or "INBOX")
        imap_config["username_env"] = str(
            answer.get("username_env") or imap_config.get("username_env") or "AI_NEWS_IMAP_USERNAME"
        )
        imap_config["password_env"] = str(
            answer.get("password_env") or imap_config.get("password_env") or "AI_NEWS_IMAP_PASSWORD"
        )
        print(f"[next] 抓取 Newsletter 前，请先设置环境变量 {imap_config['username_env']} 和 {imap_config['password_env']}")
        return

    if choice == "mcp":
        add_enabled_source(config, "email")
        email_config["mode"] = "mcp"
        print("[next] 请确认当前 Agent runtime 已注册 Gmail / 邮件 MCP server，且具备搜索 + 读取邮件正文的权限。")
        print("[next] MCP 模式无独立烟测脚本；首次跑日报时由 Agent 直接通过 MCP 工具按发件人 + 日期检索 Newsletter。")
        return

    email_config["mode"] = "none"
    remove_enabled_source(config, "email")
    if choice == "later":
        print("[next] Newsletter 接入已标记为稍后配置")
    else:
        print("[ok] 已关闭 Newsletter 来源")
    print("[next] 之后想接入 Newsletter，可对 agent 说“重新配置 Newsletter”，或运行：python3 scripts/init.py --reconfigure newsletter")


def apply_output_dir_answer(config: dict[str, Any], output_dir: Any) -> None:
    paths = config.setdefault("paths", {})
    paths["output_dir"] = str(output_dir or paths.get("output_dir") or "~/ai-news-keji/output")
    mark_setup_step(config, "output_dir_selected")


def apply_preferences_answer(config: dict[str, Any], skill_root: Path, preferences: Any, dry_run: bool = False) -> None:
    setup = config.setdefault("setup", {})
    mark_setup_step(config, "preferences_prompted")
    text = str(preferences or "").strip()
    if text:
        setup["preferences_configured"] = write_preferences_file(config, skill_root, text, dry_run=dry_run, overwrite=True)
        return
    setup["preferences_configured"] = False
    print("[ok] 未填写个人偏好，将使用内置默认筛选逻辑")


def apply_guided_answers(config: dict[str, Any], skill_root: Path, answers: dict[str, Any], dry_run: bool = False) -> None:
    if not isinstance(answers, dict):
        raise ValueError("answers-file 顶层必须是 JSON object")

    mark_setup_step(config, "external_skills_prompted")
    apply_newsletter_answer(config, answers.get("newsletter", "later"))
    apply_output_dir_answer(config, answers.get("output_dir"))
    apply_preferences_answer(config, skill_root, answers.get("preferences", ""), dry_run=dry_run)
