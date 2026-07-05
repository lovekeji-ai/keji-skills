**中文** | [English](README.en.md)

# ai-news-keji

> AI / 科技新闻日报 Skill。让高质量信息源替你筛一遍，再让 Agent 替你跨源去重、按你的兴趣评分、整理成可直接放进 Obsidian 的每日摘要。

这不是又一个信息流阅读器，而是"让信息来找你"的个人情报系统骨架。你不用每天打开 AI HOT、5 个 Newsletter 网站、刷 X、翻 RSS 阅读器——只要在 Agent 里说一句"生成今天的 AI 日报"，剩下的事它替你完成。

## 你能拿到什么

每天两份 Markdown，写到你指定的目录（默认 `~/ai-news-keji/output`）：

```text
2026-04-25.md          # 原始稿：每个来源一节，按时间和分类组织
2026-04-25 摘要.md     # 摘要稿：按"行业雷达 + 个人价值"两条轨道整理
```

摘要默认包含四块（详见 [prompts/summary-template.md](prompts/summary-template.md)）：

- 今日行业大事
- 今日对我有用
- 值得关注
- 今日关键信号

跨天会自动维护一份滚动事件库，把已经报道过的旧闻识别为"延续报道"并降权，不让同一件事在你 feed 里反复出现。

## 设计思路：三层过滤

```text
重型聚合器
AI HOT / BestBlogs / 量子位 / Readwise 等，从全网吸入信息
        ↓
编辑精选层
TLDR / The Rundown AI / Ben's Bites / The Neuron 等，由编辑团队二次筛选
        ↓
独家视角层
Latent.Space / DeepLearning.AI / 个人原创 Newsletter 等，提供不可替代的判断
        ↓
你的每日摘要
跨源去重、按兴趣评分、写入 Markdown
```

默认偏 AI 和科技，但保留了工程、创业、创作者经济、设计、跨领域思考的位置，避免日报变成同质化的 AI 快讯堆叠。

## Quick Start

1. 把这个 skill 注册到你的 Agent（Claude Code / Codex，命令见文末）
2. 在 Agent 里说：`/ai-news-keji` 或 "生成今天的 AI 日报"
3. **第一次会触发对话式初始化**——Agent 弹选项卡问你 4 个问题，全部点选完成，不需要手敲配置

AI HOT 已作为默认信息源接入，不需要 API Key、登录或额外安装；初始化问题里的"外部集成"只针对 `follow-builders` / `BestBlogs` / `ak-rss-digest` 这些可选增强来源。

设置完成后，每次说一声就生成当天日报。不需要打开任何 YAML、不用记任何命令。

## 第一次会发生什么

Agent 检测到首次运行时，会用 `AskUserQuestion` 工具一步步引导，每一步都是点选式（每个选项都允许"其他"自定义）：

| 步骤 | 它会问 |
| --- | --- |
| 1. 外部集成 | 是否启用 `follow-builders` / `BestBlogs` / `ak-rss-digest`（多选，已装的会自动检测并标注） |
| 2. Newsletter 接入 | `IMAP`（标准邮箱）/ `MCP`（已注册 Gmail MCP server 的 Agent 环境）/ 稍后 / 不接入 |
| 2.1 IMAP 凭据 | 仅在选 IMAP 时出现：邮箱 host、文件夹、账号 / 密码环境变量名（账号密码只走环境变量，不进配置文件） |
| 3. 输出目录 | 默认 `~/ai-news-keji/output`，或自定义 |
| 4. 个人画像 | 工程 / 研究 / 创业 / 自定义偏好——会写进本地 `filter-rules.md`，决定评分和摘要重点 |

启用 BestBlogs 时，Agent 还会检测 `bestblogs` 是否已登录，未登录会提示你去 [bestblogs.dev/settings](https://bestblogs.dev/settings) 拿 API Key 并就地完成 `bestblogs auth login`。

## 日常使用

```text
生成今天的 AI 日报
生成 2026-04-25 的日报
刷新日报
/ai-news-keji
```

如果当天已有产物，Agent 会先问你三选一：

- **使用已有结果** — 直接给路径
- **补充抓取** — 保留已有内容，只追加新条目，重写摘要；如果检测到某些 heavy external source 只跑到了 raw cache，这一项也会优先补完它们的 normalization
- **重新抓取并覆盖** — 清空缓存重跑（会覆盖你已经看过的版本，所以默认要确认）

从现在开始，Agent 不只检查“有没有文件”，还会检查“是不是只跑了一半”。例如：

- 已经有 raw cache，但还没有摘要稿
- `AI HOT` / `follow-builders` / `bestblogs` / `ak-rss-digest` 只有原始输出，还没完成 deterministic normalization

这类情况会被识别为 partial run，优先引导你补跑，而不是误覆盖。

## 之后想改什么，直接说

所有设置都能通过对话改回去，**不用碰配置文件**：

- "重新配置 Newsletter" / "改成 MCP 接入"
- "换输出目录到 ~/Documents/ai-news-keji"
- "重新选外部集成"
- "更新个人偏好——更关注 agent 框架和工程实践"
- "把摘要写得更短"

Agent 会重新触发对应那一步的选项卡，其他配置保持不动。

## 默认信息源

公开配置默认启用 AI HOT；RSS、Newsletter、外部 Skill 和 Website 来源在 [`sources.example.yaml`](sources.example.yaml) 里维护，你可以按需删减或新增。AI HOT 不放在 `sources.yaml` 里，因为它是内置 API 来源，由 `scripts/fetch-aihot.py` 负责抓取、分页和日期过滤。

| 类型 | 默认条目 | 用途 |
| --- | --- | --- |
| API | AI HOT | 中文 AI 热点精选；匿名 REST API，无需 token，在 `config.example.yaml` 的 `pipeline.enabled_sources` 里启用 |
| RSS | 量子位、三花 AI 快讯 | 中文 AI 媒体作为基础盘 |
| Newsletter | TLDR (AI / Dev / Founders)、The Rundown AI、The Neuron、AI Breakfast、AI Valley、Ben's Bites | 编辑精选层，判断"今天什么重要" |
| 外部 Skill / CLI | follow-builders、BestBlogs、ak-rss-digest | 接入 X、播客、独立博客集合 |
| Website | Readwise Weekly | 用读者高亮行为发现长内容 |

每个源都可以单独设置 `frequency`：

| frequency | 行为 |
| --- | --- |
| `daily` | 每次都查 |
| `weekday` | 周末跳过 |
| `3x_week` | 每次都查，没新内容也正常 |
| `weekly` | 一周内已成功抓取就跳过 |
| `irregular` | 每次都查，没新内容也正常 |

要换源？告诉 Agent："增加 Stratechery 这个 Newsletter" 或直接编辑 `sources.yaml`——两种方式都可以。

## Newsletter 接入：IMAP vs MCP

Newsletter 是日报里信号密度最高的来源，但邮件读取需要凭据。两种接入方式：

| | IMAP | MCP |
| --- | --- | --- |
| 适用邮箱 | 任意标准邮箱（Gmail / iCloud / Outlook / QQ / 163…） | 取决于 MCP server，目前主要是 Gmail / Workspace |
| 凭据 | App Password / 授权码，存本机环境变量 | OAuth，由 MCP server 管理；本仓库不存凭据 |
| 故障定位 | 链路短，能独立验证 | MCP server 是黑盒，调试要看 runtime 日志 |
| 运行环境 | 任何 Python 环境都能跑 | 必须在已注册对应 MCP server 的 Agent runtime 内 |

**经验法则**：默认选 IMAP；已经在用 Gmail MCP 才选 MCP。

Agent 在初始化第 2 步会问你选哪种；事后改主意说一句"换成 MCP 接入 Newsletter"就能切换。

## 三个可选外部集成

它们默认关闭，Agent 在初始化第 1 步会问你要不要装：

| 名称 | 作用 | 备注 |
| --- | --- | --- |
| [follow-builders](https://github.com/zarazhangrui/follow-builders) | 追踪顶尖 AI builders 的 X、播客和官方博客 | git 形态 skill |
| [BestBlogs](https://github.com/ginobefun/bestblogs) | 精选技术 / AI / 产品深度内容 | npm CLI；**必须 `bestblogs auth login` 才有数据**。`discover today --json` 常只给候选摘要，很多条目的真实 URL 需要再用 `bestblogs read deep <resourceId>` 获取；若遇到 `RATE_LIMITED` / `429`，应记录为待下轮补抓，而不是误判为“无链接”。 |
| [ak-rss-digest](https://github.com/rookie-ricardo/erduo-skills) | 大集合的独立博客 RSS + AI 评分摘要 | git 形态 skill |

不装也能用——就是少几个高质量信号源。

## Heavy external source 的安全落库方式

像 `AI HOT`、`follow-builders`、`BestBlogs`、`ak-rss-digest` 这类来源，会返回聚合 JSON、候选摘要、tweet 列表或超长 transcript。现在推荐固定走两步：

1. **先缓存 raw**：保留上游原始输出，便于排错与重试
2. **再做 deterministic normalization**：把 raw 转成统一的中间 JSON，再交给 Agent 去重、评分、写稿

对应脚本：

```bash
python3 scripts/fetch-aihot.py --date YYYY-MM-DD --output /path/to/aihot.json
python3 scripts/normalize-external-source.py --source aihot --input /path/to/aihot.json --output /path/to/aihot-normalized.json
python3 scripts/normalize-external-source.py --source follow-builders --input /path/to/follow-builders.json --output /path/to/follow-builders-normalized.json
python3 scripts/normalize-external-source.py --source bestblogs --input /path/to/bestblogs.json --output /path/to/bestblogs-normalized.json --deep-read-bestblogs
python3 scripts/normalize-external-source.py --source ak-rss-digest --input /path/to/ak-rss.json --output /path/to/ak-rss-digest-normalized.json
```

这样做的好处：

- 不把整段 transcript / prompt / 汇总文案直接塞进日报
- `AI HOT` 通过匿名 REST API 抓取精选条目，脚本内置必要 User-Agent，并按目标日期过滤
- `BestBlogs` 可以把 `discover` 与 `read deep` 区分开：有链接、待补抓、限流、纯推荐摘要分别标记
- `check-run-state.py` 可以识别“只有 raw、还没 normalize”的半成品状态

## Hermes 本地安装防漂移同步

为了避免出现“源码仓库改了，但 Hermes 实际仍在用旧副本”的漂移，这个 skill 现在推荐使用：

- 源码工作副本：`~/Code/ai-news-keji`
- Hermes 实际加载目录：`~/.hermes/skills/research/ai-news-keji`
- 同步方式：**保留 Hermes skill 目录本身为真实目录，但把共享文件/目录改成指向源码仓库的内部符号链接**
- 本地私有文件（例如 `config.yaml`、`sources.yaml`、`.venv/`、`.git/`）继续只保留在 Hermes 目录里，不跟源码仓库混在一起

这样做的好处：

1. Hermes skill discovery 更稳定：不依赖“整个 skill 目录是一个 symlink”这种容易出问题的方式。
2. 你在源码仓库里改 `SKILL.md`、`README.md`、`scripts/`、`prompts/`、`references/` 后，Hermes 会立刻读到最新内容。
3. 本地凭据、虚拟环境和用户配置不会被误带进源码仓库。

已提供同步脚本：

```bash
~/Code/ai-news-keji/scripts/sync-hermes-skill.sh
```

它会：

- 先备份当前 Hermes skill 到 `~/.hermes/skills/research/_backups/ai-news-keji-<timestamp>/`
- 再把共享文件重新链接到源码仓库
- 保留 `config.yaml`、`sources.yaml`、`.venv/`、`.git/` 等本地项

适用时机：

- 你手动改过 Hermes 目录，想重新对齐到源码仓库
- 你新增了需要共享到 Hermes 的脚本或文档
- 你怀疑两边内容已经发生漂移

## 隐私

这套流程会处理 Newsletter 正文、邮件、个人筛选规则和本地知识库路径。默认 `.gitignore` 已经排除：

- `config.yaml`、`sources.yaml`（你的本地配置）
- `.env*`、`.venv/`、`cache/`（凭据和本地产物）

凭据**只通过环境变量或第三方 OAuth 提供**，永远不会写进 `config.yaml`。`paths.cache_dir` 默认在仓库外（`~/.cache/ai-news-keji`），原始邮件缓存也不会被提交。

## 安装

### 1. 拉仓库 + 装依赖

```bash
git clone https://github.com/lovekeji-ai/ai-news-keji.git
cd ai-news-keji
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

### 2. 注册到你的 Agent

Claude Code：

```bash
mkdir -p ~/.claude/skills
ln -sfn "$(pwd)" ~/.claude/skills/ai-news-keji
```

Codex：

```bash
mkdir -p ~/.codex/skills
ln -sfn "$(pwd)" ~/.codex/skills/ai-news-keji
```

### 3. 在 Agent 里召唤

```text
/ai-news-keji
```

Agent 会接管之后的初始化和日常使用。

## 维护者参考

仓库里有几个内部脚本，**普通用户不需要直接调用**——日常流程全部由 Agent 走 SKILL.md 触发。下面这些只在排错或开发时用：

- 健康检查：`.venv/bin/python scripts/doctor.py`
- 强校验闸门：`.venv/bin/python scripts/init.py --check`
- 编译检查：`.venv/bin/python -m py_compile scripts/*.py`
- 发布前确认私有文件已 ignore：`git status --short --ignored`

详细的 Agent 工作流（步骤、缓存、去重、评分逻辑）见 [SKILL.md](SKILL.md)。

## License

MIT. See [LICENSE](LICENSE).
