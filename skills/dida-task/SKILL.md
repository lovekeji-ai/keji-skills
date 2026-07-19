---
name: dida-task
description: 滴答清单（Dida365）任务管理工具。通过官方 OpenAPI + 私有 API，让 agent 能读取（任务、清单、已完成任务、番茄/专注统计）和写入（创建、更新、完成、删除任务和清单）滴答清单的数据。当用户提到"滴答"、"dida"、"清单"、"todo"、"任务"、"提醒"、"番茄钟"、"专注"且明显是要操作清单 App 时使用。不支持 TickTick 国际版，只支持国内 dida365。
---

# Dida-Task：滴答清单 Agent 工具

让 agent 完全打通滴答清单（Dida365）：读、写、统计一应俱全。

## 何时使用

**触发场景：**
- 用户要写任务到滴答："加个任务"、"提醒我..."、"加到 dida / 滴答"
- 用户要读滴答数据："今天完成了哪些任务"、"我有哪些清单"、"专注了多久"
- 用户要统计/复盘："这周完成了什么"、"花了几个番茄在 X 上"

**不要触发：**
- 用户的"任务"明显指当前对话工作项，不是 App 里的任务
- 用户在专门的 GTD 笔记系统里操作（除非明确说"同步到滴答"）

## 首次使用

凭证未配置时，先引导用户走 setup：

```bash
python3 scripts/dida.py setup
```

详细引导见 [setup.md](setup.md)。

## 能力速查

所有命令统一入口：`python3 scripts/dida.py <子命令>`

### 读

| 命令 | 作用 |
|---|---|
| `read list-projects` | 列所有清单 |
| `read list-columns <project>` | 列 kanban 清单的分组（columns） |
| `read list-tasks <project>` | 列某清单下未完成任务 |
| `read get-task <task-id>` | 拿单个任务详情 |
| `read search <关键词>` | 全量任务模糊搜索（按标题/内容） |
| `read today` | **跨清单**：今日到期的未完成任务，按清单分组 |
| `read upcoming [--days N]` | **跨清单**：未来 N 天（默认 7）到期 |
| `read by-tag <tag> [--prefix]` | 按标签筛选；`--prefix` 含子标签（如 `12wy` 匹配 `12wy/a`） |
| `read list-tags` | 列出账号所有标签（含父子关系、颜色） |
| `read completed-today` | 今天已完成任务 |
| `read completed-range <from> <to>` | 按日期范围拉已完成任务 |

### 番茄/专注

| 命令 | 作用 |
|---|---|
| `pomo today` | 今天专注总时长 + 段数 |
| `pomo by-task <task-id-或关键词>` | 某任务花了几个番茄 / 多少分钟 |
| `pomo stats <from> <to>` | 按日期范围的专注统计（heatmap + 项目分布） |

### 写

| 命令 | 作用 |
|---|---|
| `write create-task --title <标题> [选项]` | 创建任务 |
| `write update-task <task-id> [选项]` | 更新任务 |
| `write complete-task <task-id>` | 标记完成 |
| `write delete-task <task-id>` | 删除任务（默认 dry-run） |
| `write add-subtask <task-id> --title <标题>` | 给任务追加一个子任务（checklist 项） |
| `write complete-subtask <task-id> <子任务-id-或关键词>` | 标记某子任务完成 |
| `write create-project --name <名字> [选项]` | 创建清单 |
| `write update-project <project-id> [选项]` | 更新清单 |
| `write delete-project <project-id>` | 删除清单（默认 dry-run） |

**`create-task` / `update-task` 选项：**

| 参数 | 说明 |
|---|---|
| `--content <文本>` | 备注内容 |
| `--project <id\|名字>` | create-task：目标清单（默认收件箱）；update-task：**移动到该清单** |
| `--priority {0,1,3,5}` | 0 无 / 1 低 / 3 中 / 5 高 |
| `--due <YYYY-MM-DD[THH:MM]>` | 截止时间 |
| `--all-day` | 全天任务（忽略时分） |
| `--repeat "RRULE:..."` | 重复规则，如 `RRULE:FREQ=WEEKLY;BYDAY=MO` |
| `--column <id\|名字>` | kanban 分组（需配合 `--project`） |
| `--tags "a,b,c"` | 标签数组，逗号分隔 |
| `--items "step1\|step2\|step3"` | 子任务（仅 create-task；竖线分隔，自动设 `kind=CHECKLIST`） |

### 元

| 命令 | 作用 |
|---|---|
| `setup` | 首次配置（OAuth + cookie） |
| `refresh-token` | OAuth token 过期时重走授权 |
| `refresh-cookie` | Cookie 失效时引导更新 |
| `health` | 检查 token / cookie 状态 |

所有命令支持 `--json` 输出结构化数据，方便 agent 解析。

## Agent 使用准则

1. **写操作默认确认**：`delete-task` / `delete-project` 默认 dry-run，加 `--confirm` 才真删
2. **批量写入要分步**：一次创建多个任务时，先列计划→等用户确认→再调 API
3. **批量必须限速**：官方 API 限流 **100 req/min per token**（滚动 60s 窗口，超限返回 HTTP 500 `exceed_query_limit`，**不是 429**）。批量写入每条 sleep 1s，超过 50 条每 20 条歇 30s。注意 `update-task`/`delete-task`/`complete-task` 内部会调 `_find_project_id_of_task`，最坏遍历所有清单（N+1 次调用），是隐藏的限流杀手 —— 大批量操作前先 `read list-projects` 拿到 project id 直接传，能少一半请求
4. **凭证失败要给指引**：API 401/500 access_forbidden 时，**不要重试**，告诉用户跑哪个 refresh 命令
5. **限流触发等满 60 秒**：触发 `exceed_query_limit` 后等满 60s，不是 30s（滚动窗口）
6. **输出尊重用户语境**：用户问中文就用中文回，时间用北京时间

## 详细文档

- [setup.md](setup.md) — 首次配置完整流程（如何申请 client_id、拿 cookie）
- [api-reference.md](api-reference.md) — 官方 + 私有 API 端点速查
- [examples/usage.md](examples/usage.md) — 常见用法示例

## 重要声明

**已完成任务读取、番茄统计走的是滴答的私有 API**（非官方公开），用 cookie 鉴权：
- 优点：功能完整（官方 OpenAPI 没有这些能力）
- 风险：滴答随时可能改、cookie 会过期（几周到几个月）
- 失败时 skill 会给出明确的 refresh 指引，不会卡死

所有**写操作**（建任务/改任务/删任务）走官方 OpenAPI，稳定可靠。
