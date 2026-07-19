# Dida-Task

滴答清单（Dida365）Agent 工具。它把国内版滴答清单接到支持 Skill 机制的 AI agent 里，让 agent 可以读取任务、清单、已完成记录和番茄/专注统计，也可以创建、更新、完成、删除任务和清单。

这是一个 Skill 工具包，不是独立 App，也不是 MCP server。

## 适合谁

适合：

- 想让 AI 助手直接操作个人滴答清单的国内版 Dida365 用户
- 想用自然语言完成「加个任务」「提醒我」「今天完成了什么」「这个任务花了几个番茄」这类操作的人
- 想在复盘、周报、计划整理时把滴答任务和专注数据交给 agent 汇总的人

不适合：

- TickTick 国际版用户：只支持国内 `dida365.com`，两个版本账号和数据不互通
- 需要托管服务、团队产品或商业化集成的场景：私有 API 部分仅建议个人使用
- 期待 MCP 协议接入的场景：当前只是 Skill + CLI，未来可以再扩展

## 核心能力

Dida-Task 同时使用两类接口：

- 官方 OpenAPI：用于稳定地读清单/未完成任务，以及创建、更新、完成、删除任务和清单
- 浏览器私有 API：用于读取官方 OpenAPI 暂不提供的已完成任务、全量搜索、番茄和专注统计

这意味着你可以按需配置：

- 只配置 OAuth：可写任务、读清单、读未完成任务
- OAuth + cookie 都配置：解锁已完成任务、搜索、番茄和专注统计

## 安装

把仓库放进你的 agent skills 目录。以 Claude Code 为例：

```bash
cp -r dida-task ~/.claude/skills/
```

进入 skill 目录后完成首次配置：

```bash
cd ~/.claude/skills/dida-task
python3 scripts/dida.py setup
python3 scripts/dida.py health
```

详细配置流程见 [setup.md](setup.md)，包括如何申请 `client_id`、`client_secret`，以及如何从浏览器复制 cookie。

## 快速使用

所有能力都走同一个入口：

```bash
python3 scripts/dida.py <command> [options]
```

常见例子：

```bash
# 查看所有清单
python3 scripts/dida.py read list-projects

# 查看今天到期的未完成任务
python3 scripts/dida.py read today

# 创建任务
python3 scripts/dida.py write create-task --title "写周报" --project 工作 --due 2026-06-05

# 创建带子任务和标签的 checklist
python3 scripts/dida.py write create-task \
  --title "发布文章" \
  --project 内容 \
  --tags "writing,publish" \
  --items "校对正文|配图|发到公众号"

# 查看今天专注统计
python3 scripts/dida.py pomo today
```

所有读写和统计命令都支持 `--json`，方便 agent 解析：

```bash
python3 scripts/dida.py read today --json
python3 scripts/dida.py pomo stats 2026-06-01 2026-06-30 --json
```

更多例子见 [examples/usage.md](examples/usage.md)。

## 命令速查

### 读任务和清单

| 命令 | 作用 | 接口 |
|---|---|---|
| `read list-projects` | 列出所有清单 | 官方 |
| `read list-columns <project>` | 列出看板清单的分组 | 官方 |
| `read list-tasks <project>` | 列出某清单下未完成任务 | 官方 |
| `read get-task <task-id> [--project-id <id>]` | 读取单个任务详情 | 官方 |
| `read today` | 跨清单列出今天到期的未完成任务 | 私有 + 官方 |
| `read upcoming [--days N]` | 跨清单列出未来 N 天到期的未完成任务，默认 7 天 | 私有 + 官方 |
| `read by-tag <tag> [--prefix]` | 按标签筛选未完成任务，`--prefix` 可匹配子标签 | 私有 + 官方 |
| `read list-tags` | 列出账号所有标签 | 私有 |
| `read search <keyword>` | 全量任务模糊搜索 | 私有 |
| `read completed-today [--limit N]` | 列出今天已完成任务 | 私有 + 官方 |
| `read completed-range <from> <to> [--limit N]` | 按日期范围列出已完成任务 | 私有 + 官方 |

### 番茄和专注

| 命令 | 作用 | 接口 |
|---|---|---|
| `pomo today` | 今天专注总时长、段数和明细 | 私有 |
| `pomo by-task <task> [--from YYYY-MM-DD] [--to YYYY-MM-DD]` | 按任务关键词统计专注时长 | 私有 |
| `pomo stats <from> <to>` | 日期范围内的 heatmap、项目、标签、任务分布 | 私有 |

### 写任务和清单

| 命令 | 作用 | 接口 |
|---|---|---|
| `write create-task --title <title> [options]` | 创建任务 | 官方 |
| `write update-task <task-id> [options]` | 更新任务；传 `--project` 可移动到其他清单 | 官方 |
| `write complete-task <task-id>` | 标记任务完成 | 官方 |
| `write delete-task <task-id> [--confirm]` | 删除任务；默认 dry-run，传 `--confirm` 才真删 | 官方 |
| `write add-subtask <task-id> --title <title>` | 给任务追加一个子任务 | 官方 |
| `write complete-subtask <task-id> <subtask>` | 按 id 或标题关键词完成子任务 | 官方 |
| `write create-project --name <name> [options]` | 创建清单 | 官方 |
| `write update-project <project-id> [options]` | 更新清单 | 官方 |
| `write delete-project <project-id> [--confirm]` | 删除清单；默认 dry-run，传 `--confirm` 才真删 | 官方 |

`create-task` 和 `update-task` 常用参数：

| 参数 | 说明 |
|---|---|
| `--title <text>` | 任务标题；创建任务时必填 |
| `--content <text>` | 备注内容 |
| `--project <id\|name>` | 清单 id 或名称；更新任务时表示移动清单 |
| `--priority {0,1,3,5}` | 优先级：0 无，1 低，3 中，5 高 |
| `--due <YYYY-MM-DD[THH:MM]>` | 截止日期或时间 |
| `--all-day` | 全天任务 |
| `--repeat "RRULE:..."` | 重复规则 |
| `--column <id\|name>` | 看板分组；需要同时指定 `--project` |
| `--tags "a,b,c"` | 标签，逗号分隔 |
| `--items "a\|b\|c"` | 子任务，竖线分隔；仅创建任务时可用 |

### 配置和健康检查

| 命令 | 作用 |
|---|---|
| `setup` | 首次配置 OAuth token 和可选 cookie |
| `refresh-token` | OAuth token 过期后重新授权 |
| `refresh-cookie` | 私有 API cookie 过期后手动更新 |
| `health` | 检查配置文件、token、cookie 和 API 可用性 |

## 凭证和安全

默认凭证文件在：

```text
~/.config/dida-task/credentials.json
```

`setup` 会把文件权限设为 `600`。也可以用环境变量覆盖配置文件：

- `DIDA_CLIENT_ID`
- `DIDA_CLIENT_SECRET`
- `DIDA_ACCESS_TOKEN`
- `DIDA_REDIRECT_URI`
- `DIDA_COOKIE_T`

不要把 `client_secret`、`access_token` 或 cookie 提交到 git，也不要公开分享截图。

## 私有 API 说明

以下能力依赖滴答网页端的非公开私有 API，并通过浏览器 cookie 鉴权：

- 已完成任务读取
- 全量任务搜索
- 标签读取
- 今日 / upcoming / by-tag 这类跨清单查询
- 番茄和专注统计

注意事项：

- 这些接口不是官方承诺的开放能力，滴答可以随时调整或关闭
- Cookie 会过期，通常需要几周到几个月手动续期一次
- 如果只需要写任务和读取未完成任务，可以在 `setup` 时跳过 cookie
- 请仅用于个人自动化，不要用于商业产品或大规模请求

所有写操作都走官方 OpenAPI，并且删除操作默认 dry-run，必须加 `--confirm` 才会真正删除。

## 文档

- [SKILL.md](SKILL.md)：Agent 使用入口和行为准则
- [setup.md](setup.md)：首次配置详细引导
- [examples/usage.md](examples/usage.md)：常见用法示例
- [api-reference.md](api-reference.md)：官方 + 私有 API 端点速查

## 参考

- [vex-glitch/TickAL-TickTick-Alfred-Workflow](https://github.com/vex-glitch/TickAL-TickTick-Alfred-Workflow)：该 Alfred workflow 说明 TickTick Open API 不暴露已完成任务，并通过本地 `completed_tasks` cache 展示完成记录。本 skill 对“官方 OpenAPI 缺少已完成任务读取能力”的判断受其启发，但当前实现改用 Dida365 私有 API 读取真实已完成任务。

## License

MIT
