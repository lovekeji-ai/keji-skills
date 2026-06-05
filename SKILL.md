---
name: ai-news-keji
description: 生成 AI/科技新闻日报：从已配置的 Newsletter、RSS、可选外部来源和网站来源抓取、去重、评分并生成 Markdown。触发：用户说"生成日报 / AI日报 / 今日新闻 / 刷新日报 / fetch news / /ai-news-keji"，或要求重新配置本 skill（"改输出目录 / 重新配置 Newsletter / 重新选外部集成 / 更新个人偏好"）。不触发：单纯"看看 BestBlogs 推荐"、"我关注的 AI builder"等请求，应交给对应的独立 skill。
---

# AI 科技新闻日报

从用户配置的信息源生成适合 Obsidian 使用的 AI/科技新闻原始稿和摘要稿。

## 交互语言

所有面向用户的说明、进度更新、错误解释和最终回复都必须使用中文。命令、文件名、配置键、环境变量、URL、产品名和 Newsletter 名称保持原样。

启动工作流时不要用英文开场，例如不要说 “I'll start...”。应使用类似“我先检查 ai-news-keji 的初始化状态。”这样的中文说明。

## 运行约束（重要）

- **所有 Python 命令默认使用 repo-local `.venv/bin/python`**，优先从实际开发仓库根目录运行，而不是盲目假设 `~/.hermes/skills/...` 就是可执行 repo。先用 `scripts/doctor.py` 确认当前环境指向的真实仓库路径；如果 doctor 输出了开发仓库（例如 `~/Code/ai-news-keji`），后续 `init.py` / `check-run-state.py` / `build-summary-context.py` / fetch 脚本都从那个 repo root 执行，确保使用同一份 `.venv`、`prompts/summary-template.md` 和最新脚本。
- **凭据只走环境变量**：IMAP 账号/密码/授权码绝不写入 `config.yaml`，只通过 `email.imap.username_env` / `password_env` 指定的环境变量提供。
- **不要把整份 raw JSON / normalized JSON / 原始稿 / transcript 直接喂给模型**。heavy source 必须先 deterministic normalization，再构建 compact context，最后才进入 LLM 总结步骤。
- **cron / 无人值守场景下的 partial-run 默认策略**：如果 `check-run-state.py` 显示 `has_existing=true`，且现有产物只有缓存、原始稿/摘要稿缺失，这类情况默认视为“补充抓取 / 补全产物”，优先复用已有缓存、补抓当前可用来源、重建 `summary-context.md`，然后补写原始稿和摘要稿；不要把这种 cache-only partial run 直接当成需要覆盖重跑的信号。
- **网站来源与 compact context 的一致性要显式验证**：抓到 `websites.json` 之后，必须确认当前 `build-summary-context.py` 是否真的把网站条目纳入 `summary-context.md`。如果没有纳入，就要么先补齐脚本/流程再依赖这些网站条目，要么明确把网站来源降级为“已缓存但未进入本轮 compact context”，不要声称它已经参与了原始稿/摘要稿生成。

## 路径

所有文件都相对于 skill 目录解析，也就是包含 `SKILL.md` 的目录。

- 本地配置：`config.yaml`
- 公开配置模板：`config.example.yaml`
- 本地来源：`sources.yaml`
- 公开来源模板：`sources.example.yaml`
- 初始化入口：`scripts/init.py`
- 初始化向导：`scripts/init_wizard.py`
- 运行状态检查：`scripts/check-run-state.py`
- 摘要模板：`prompts/summary-template.md`
- 健康检查：`scripts/doctor.py`
- RSS 抓取脚本：`scripts/fetch-rss.py`
- IMAP 邮件抓取脚本：`scripts/fetch-email-imap.py`
- 外部重型来源 normalization：`scripts/normalize-external-source.py`

运行工作流前：

1. 在 skill 目录运行 `.venv/bin/python scripts/init.py --check`。
2. 如果检查因为缺少 PyYAML 失败，运行 `.venv/bin/python -m pip install -r requirements.txt`，然后重试一次检查。
3. 如果检查提示首次启动、缺少 `config.yaml`、缺少 `sources.yaml`、`setup.initialized is not true`，或“尚未完成初始化向导”，进入 Agent 分步初始化流程。优先使用 `init.py --check` 输出里的“建议开场”和“第 1 步问题”作为下一条用户消息；如果检查输出里没有这两段，运行 `.venv/bin/python scripts/init.py` 获取同样的分步提示。
4. 初始化首轮消息固定只包含开场和第 1 步外部集成问题。第 1 步完成前，当前轮不读取 `config.example.yaml` 或 `sources.example.yaml`，也不展示 Newsletter、IMAP、输出目录或个人偏好问题。
5. 分步初始化每轮只处理当前步骤；每一步都先用一句话说明这一步的作用，**然后必须调用 `AskUserQuestion`** 让用户用选项卡形式作答，不要让用户在普通对话里手敲文字回答。每步的选项设计、字段、文案细节见 `references/init-flow.md`；以 `init.py` / `init_wizard.py` 输出的"建议开场"和分步问题为准。用户提交答案后再推进下一步。
6. 收集完全部答案后，把答案写入临时 JSON 文件，然后运行 `.venv/bin/python scripts/init.py --answers-file <answers.json>`。JSON 字段：`external_skills`、`newsletter.choice`、`newsletter.host`、`newsletter.folder`、`newsletter.username_env`、`newsletter.password_env`、`output_dir`、`preferences`。
7. 写入配置后再次运行 `.venv/bin/python scripts/init.py --check`。只有检查通过后，才继续读取 `config.yaml`、`sources.yaml` 并抓取新闻。
8. 可选外部 skills 或 CLI 只根据用户在初始化回答里的选择安装。
8.1 用户事后想改某一步配置（"重新配置 Newsletter / 改输出目录 / 改个人偏好 / 重新选外部集成"），走 `--reconfigure`：先运行 `.venv/bin/python scripts/init.py --reconfigure {external_skills|newsletter|output_dir|preferences}` 获取该步的 `AskUserQuestion` 指令，收集答案后运行 `.venv/bin/python scripts/init.py --answers-file <answers.json> --reconfigure <section>` 写回 `config.yaml`，其他步骤保持原值不动。**区分**：仅追加安装一个外部 skill（不改任何已有答案）才用 `--skills <name>`；任何涉及"重新选 / 改回答"的场景都走 `--reconfigure`。
9. 解析路径时展开 `~` 和环境变量。
10. 不要把私有输出、原始邮件缓存、token 或用户专属配置写进准备发布的文件。

## 配置

使用 `config.yaml` 控制行为：

- `paths.output_dir`：原始稿和摘要 Markdown 的写入目录
- `paths.filter_rules`：评分规则和兴趣画像；未设置或文件缺失时使用内置示例
- `paths.cache_dir`：原始来源数据和滚动去重状态的缓存目录
- `settings.default_date`：`yesterday` 或 `today`
- `settings.retention_days`：缓存清理窗口
- `settings.dedup_window_days`：跨天去重窗口
- `settings.timezone`：日期过滤时区
- `pipeline.enabled_sources`：要尝试的来源组，例如 `rss`、`email`、`external_skills`、`websites`
- `pipeline.skip_unavailable_sources`：缺少工具或凭据时跳过对应来源，而不是直接失败
- `email.mode`：`none`、`imap` 或 `mcp`
- `email.imap.*`：IMAP host、folder 和凭据环境变量名
- `external_skills.*`：可选命令；只运行 `enabled: true` 的条目
- `notification.method`：`none`、`macos` 或其他用户配置方式

配置不确定时，运行健康检查：

```bash
.venv/bin/python scripts/doctor.py
```

缺少本地配置时，在 Agent 对话中收集初始化答案，然后写入临时 JSON 并运行：

```bash
.venv/bin/python scripts/init.py --answers-file <answers.json>
```

抓取来源前，工作流必须通过这个检查：

```bash
.venv/bin/python scripts/init.py --check
```

初始化检查通过后、抓取任何来源前，必须检查目标日期是否已经有运行产物：

```bash
.venv/bin/python scripts/check-run-state.py --date YYYY-MM-DD --config config.yaml
```

如果输出里的 `has_existing` 为 `true`，除非用户在原始请求中明确说“强制刷新 / 覆盖重跑 / 忽略已有文件”，否则必须先停下来询问用户如何处理，不要直接抓取。除了 `existing_kinds`，还要检查：

- `is_partial_run`
- `partial_reasons`
- `source_states`

用单选提问，先说明检测到哪些已有产物、哪些来源只跑了一半，再提供这些选项：

- `使用已有结果`：不抓取新数据。若摘要稿已存在，直接报告原始稿和摘要稿路径；若只有原始稿存在，则基于已有原始稿生成摘要。
- `补充抓取`：保留已有原始稿和缓存，只抓取当前可用来源的新内容；如果某个 heavy external source 只有 raw cache、还没完成 normalization，这个选项也负责先补完 normalization，再追加新条目并重写摘要。
- `重新抓取并覆盖`：清空目标日期缓存并覆盖当天原始稿和摘要稿；这个选项会覆盖已有结果，必须在说明里明确提醒。

## 频率规则

`sources.yaml` 里的每个来源都可以包含 `frequency`：

| frequency | rule |
| --- | --- |
| `daily` | 每次运行都检查。 |
| `weekday` | 目标日期是周六或周日时跳过。 |
| `3x_week` | 每次运行都检查；没有新内容是正常情况。 |
| `weekly` | 如果缓存显示最近 7 天已成功抓取，则跳过。 |
| `irregular` | 每次运行都检查；经常没有新内容是正常情况。 |

被跳过的来源不是失败，也不应该生成空章节。

## 工作流

默认使用 `settings.default_date` 选择的日期。如果用户指定了日期，使用用户指定的日期。

### 1. 检查已有产物

先运行：

```bash
.venv/bin/python scripts/check-run-state.py --date YYYY-MM-DD --config config.yaml
```

如果目标日期已经存在原始稿、摘要稿或缓存：

1. 用中文告诉用户检测到的已有产物，例如“检测到 2026-04-25 已经有原始稿和 RSS 缓存”。
2. 询问用户选择 `使用已有结果`、`补充抓取` 或 `重新抓取并覆盖`。
3. 用户未选择前，不抓取 RSS、Email、外部 skills 或网站来源。
4. 选择 `使用已有结果` 时，不改写已有原始稿；如摘要稿存在，直接结束并报告路径；如摘要稿不存在，只执行“生成摘要”步骤。
5. 选择 `补充抓取` 时，继续后续抓取流程；若 `partial_reasons` 显示某个来源只有 raw cache，则先基于现有 raw cache 补跑 normalization，再决定是否需要重抓上游。写入原始稿时只追加新增内容，不删除已有内容。
6. 选择 `重新抓取并覆盖` 时，先说明会覆盖目标日期文件；只有用户明确选择后，才清空 `{paths.cache_dir}/YYYY-MM-DD/` 并覆盖 `{paths.output_dir}/YYYY-MM-DD.md` 与摘要稿。

如果没有已有产物，继续正常抓取。

### 2. 抓取来源

工具可用时，并行抓取已启用的来源组。

**RSS**

在 skill 目录运行：

```bash
.venv/bin/python scripts/fetch-rss.py --date YYYY-MM-DD --config sources.yaml
```

如果缺少 `sources.yaml`，脚本会回退到 `sources.example.yaml`。

**Email Newsletter**

只有当 `pipeline.enabled_sources` 启用了 `email` 时，才使用已配置的 `email` 来源白名单。

支持的模式：

- `none`：跳过邮件来源。
- `imap`：运行内置 IMAP 抓取脚本。凭据必须来自 `email.imap.username_env` 和 `email.imap.password_env` 指定的环境变量。
- `mcp`：当当前 Agent 运行环境提供 email/Gmail MCP 工具时使用该工具。

使用 IMAP 时，在 skill 目录运行：

```bash
.venv/bin/python scripts/fetch-email-imap.py --date YYYY-MM-DD --config config.yaml --sources sources.yaml
```

IMAP 抓取脚本会搜索目标日期，用 `BODY.PEEK[]` 读取邮件以避免标记为已读，根据配置的发件人和可选 `subject_contains` 过滤邮件，尽可能提取纯文本，并把 JSON 输出到 stdout。

使用 MCP 时，搜索目标日期的邮件，根据配置的发件人和可选 subject 规则过滤，读取匹配邮件，并跳过欢迎邮件、订阅确认、纯赞助邮件、广告和招聘内容。

如果 IMAP 凭据或 MCP 工具不可用，且 `pipeline.skip_unavailable_sources` 为 true，则跳过邮件来源，并记录该来源组不可用。

**外部 skills 和 CLI**

对每个 `enabled: true` 的 `external_skills.*` 条目，运行其配置的命令。命令缺失、目录缺失或非零退出都视为来源失败；如果 `pipeline.skip_unavailable_sources` 为 true，则跳过并记录原因。

对外部 skills 的结果要做可落库性检查。对 `follow-builders`、`bestblogs`、`ak-rss-digest` 这类 heavy external source，必须先缓存 raw，再运行 deterministic normalization，最后才把 normalized items 带进写稿与摘要流程：

```bash
.venv/bin/python scripts/normalize-external-source.py --source follow-builders --input {cache_dir}/YYYY-MM-DD/follow-builders.json --output {cache_dir}/YYYY-MM-DD/follow-builders-normalized.json
.venv/bin/python scripts/normalize-external-source.py --source bestblogs --input {cache_dir}/YYYY-MM-DD/bestblogs.json --output {cache_dir}/YYYY-MM-DD/bestblogs-normalized.json --deep-read-bestblogs
.venv/bin/python scripts/normalize-external-source.py --source ak-rss-digest --input {cache_dir}/YYYY-MM-DD/ak-rss.json --output {cache_dir}/YYYY-MM-DD/ak-rss-digest-normalized.json
```

然后再继续下面这些规则：

- 默认优先保留带直达原文链接的候选；有链接的条目在排序、归并和摘要时优先级更高。
- 如果外部输出是超长转录、整段 Prompt、整份 digest 或明显未结构化的大块文本，先做源适配和事实抽取；如果当前轮做不到稳定抽取，就整源跳过并记录原因，不要把长噪音直接带进日报。
- `follow-builders` 一类含长 podcast transcript / prompt 模板 / 汇总摘要的来源，默认不能整段直写，必须先拆成独立事件或明确跳过。
- `bestblogs` 的 `discover ... --json` 结果里，`readUrl` 可能为 `null`。不要因为首层 JSON 没给链接就判定“无原文链接”。如果条目带有 `resourceId`，必须先尝试运行 `bestblogs read deep <resourceId>` 拉取详情；这个详情通常会返回可落库的 canonical URL 和正文 Markdown。
- 如果通过 `bestblogs read deep <resourceId>` 成功拿到 URL，就按正常有链接条目处理，并优先使用 deep read 返回的 URL 作为原始稿和摘要稿链接。
- 如果 `bestblogs read deep <resourceId>` 命中 `RATE_LIMITED` / `429`，不要误记为“BestBlogs 无链接”。应把该来源标记为“本轮 deep read 受限流影响，待下轮补抓”，并保留 discover 层候选信息，方便下一轮或次日重试。
- 只有在 `readUrl` 为空、`resourceId` 不可用，或 `bestblogs read deep <resourceId>` 明确失败且不是限流时，才把该条目当作 BestBlogs 推荐摘要写入；此时必须明确标注它来自 BestBlogs 推荐、属于二手摘要、缺少直达原文链接，不要把它伪装成已核验的一手来源。
- 对仍然没有原文链接的外部候选，摘要时应降低置信度和优先级；优先保留那些标题具体、摘要信息量足够、并且和用户关注方向强相关的条目。
- 把 `follow-builders`、`bestblogs`、`ak-rss-digest` 视为 heavy external source：先缓存 raw，再做 deterministic normalization，再把 normalized items 交给去重/评分/写稿流程；不要把整段 transcript、tweet dump、prompt 或聚合摘要直接喂进日报。
- `check-run-state.py` 返回 `is_partial_run` / `partial_reasons` / `source_states` 时，优先把它解释为“该日期可能只跑了一半”。如果用户没明确要求覆盖，先选择补完 normalization 或补生成摘要，而不是直接重抓覆盖。
- 对这类改造或流程重构，默认由代理自己完成验证：至少跑 byte-compile、`doctor.py`、heavy-source normalization 样本，以及 `check-run-state.py` 的 partial/complete 两种 fixture。

用户明确选择外部 skills 后，可通过初始化答案写入配置；如果只是追加安装某个外部 skill，可运行：

```bash
.venv/bin/python scripts/init.py --skills follow-builders,bestblogs,ak-rss-digest
```

初始化脚本会把原始外部仓库安装到 `external_skills.install_dir` 下，并把选择的 skills 软链到 `external_skills.link_targets`。

它可以安装并启用：

- `follow-builders`：把 `zarazhangrui/follow-builders` clone 到受管理的外部 skill 目录，在其 `scripts/` 目录运行 `npm install`，并软链到已配置的 agent skill 目录。
- `bestblogs`：安装 `@bestblogs/cli`，并提示用户运行 `bestblogs auth login`；不安装 BestBlogs 对话式 agent skills。
- `ak-rss-digest`：clone `rookie-ricardo/erduo-skills`，把其中的 `skills/ak-rss-digest` 子 skill 链接到受管理的外部 skill 目录，并软链到已配置的 agent skill 目录。

**网站来源**

对 Readwise Weekly 等已配置网站来源，仅在浏览器或 web-fetch 能力可用时抓取。使用缓存避免重复抓取同一期周报。

### 3. 缓存原始数据

把原始来源数据写入 `{paths.cache_dir}/YYYY-MM-DD/`。

建议缓存文件：

```text
email-raw.json
rss-raw.json
external-skills.json
websites.json
follow-builders.json
follow-builders-normalized.json
bestblogs.json
bestblogs-normalized.json
ak-rss.json
ak-rss-digest-normalized.json
```

原始邮件缓存可能包含私人内容。请把 `paths.cache_dir` 放在公开 skill 目录之外，且不要提交缓存文件。

对 heavy external source，后续去重、评分和写稿应优先读取 `*-normalized.json`，而不是直接消费 raw 输出。

在进入原始稿/摘要稿写作前，先构建 compact context：

```bash
.venv/bin/python scripts/build-summary-context.py --date YYYY-MM-DD --config config.yaml --output {cache_dir}/YYYY-MM-DD/summary-context.md
```

后续 LLM 步骤只读取 `summary-context.md`、`prompts/summary-template.md` 和评分规则。不要再把整份 raw JSON、normalized JSON、完整原始稿或长 transcript 拉进上下文。需要核验时，只回到单条来源链接或单个缓存文件，不要整源重读。

如果 cron / agent 环境与交互式 shell 使用了不同 Python，优先保证所有 repo 命令从仓库根目录用 `.venv/bin/python` 执行。对可能被外部调度器从错误解释器拉起的脚本，可以加一个很薄的 runtime guard：先检查必需模块，再自动 re-exec 到 repo-local `.venv/bin/python`，最后才继续导入 `feedparser`、`yaml` 等依赖。

清理早于 `settings.retention_days` 的日期缓存目录。

### 4. 维护滚动去重状态

维护 `{paths.cache_dir}/recent-events.json`，保存最近 `settings.dedup_window_days` 天的事件。

对每个抓取项：

1. 提取事件核心：用一句话描述发生了什么。
2. 与最近事件比较。
3. 添加新事件。
4. 只有当延续报道提供实质新信息时才保留。
5. 删除没有新信息的重复转述。

保留延续报道时，标记为 continuation，并在评分时应用 `settings.continuation_penalty`。

### 5. 写入原始稿

写入或追加 `{paths.output_dir}/YYYY-MM-DD.md`。

原始稿要求：

- YAML frontmatter 包含 `created`、`updated`、`type` 和 `sources`
- 每个来源一个章节
- 每个条目包含加粗标题、2-5 句有用摘要和原始链接
- 不包含赞助、广告、招聘或订阅确认内容
- 长 Newsletter 内容应压缩摘要，但保留具体事实、数字、产品名、日期和链接

如果文件已存在，追加新抓取的来源章节，不删除已有内容。

### 6. 生成摘要

如果 `{paths.filter_rules}` 存在则读取它，否则使用 `references/filter-rules.example.md`。

优先读取 `{paths.cache_dir}/YYYY-MM-DD/summary-context.md`；只有在核验单条事实或修正链接时才回看原始稿/单个缓存文件。不要把完整原始稿重新喂给模型。

应用三层处理：

1. 去重并移除噪音。
2. 分别按行业雷达和个人价值两条轨道为每个事件评分。
3. 填充 `prompts/summary-template.md`，写入 `{paths.output_dir}/YYYY-MM-DD 摘要.md`，覆盖该日期的旧摘要。模板里所有 `{{...}}` 占位符必须替换为实际值，不能保留花括号、也不能整段省略。

规则：

- 不要在章节标题后立刻添加解释性文字。
- 完整条目之间用 `---` 分隔。
- 数量是参考而不是硬性配额：2-4 条行业大事、3-5 条对我有用、10-15 条值得关注、2-3 条关键信号。
- 每个事件放在最适合的章节；避免同一事件在主要章节里重复出现。
- 行业重要性不必与用户个人兴趣一致。
- 个人有用可以包括小但可执行的文章。

### 7. 通知

如果 `notification.method` 为 `macos`，只在 macOS 上使用 `osascript`。如果通知不可用或设为 `none`，静默结束，并用中文向用户报告生成的文件路径。

## 失败处理

- 配置允许跳过时，跳过不可用的可选来源。
- 在原始稿末尾记录失败来源。
- 某个 feed 格式错误或某个可选命令失败时，继续处理其他来源。
- 不要根据社交元数据猜测人物角色；有明确 profile 或 bio 字段时才使用。
- 外部评分（例如博客排名分）只作为提示，最终始终应用配置的评分规则。
