# Dida365 API 参考

本 skill 使用的所有端点速查。给 agent 在需要扩展时查阅。

## 域名

- API base（官方 + 私有共用）：`https://api.dida365.com`
- OAuth 网页域：`https://dida365.com`

**不要混用 ticktick.com**（国际版，数据账号不互通）。

---

## 官方 OpenAPI（OAuth Bearer Token）

Header：`Authorization: Bearer <access_token>`

### 项目（清单）

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/open/v1/project` | 列所有清单 |
| GET | `/open/v1/project/{id}` | 单个清单元信息 |
| GET | `/open/v1/project/{id}/data` | 清单详情（含未完成任务 + 列） |
| POST | `/open/v1/project` | 创建清单 `{name, color, viewMode}` |
| POST | `/open/v1/project/{id}` | 更新清单 |
| DELETE | `/open/v1/project/{id}` | 删除清单 |

### 任务

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/open/v1/project/{pid}/task/{tid}` | 单任务详情 |
| POST | `/open/v1/task` | 创建任务 |
| POST | `/open/v1/task/{id}` | 更新任务 |
| POST | `/open/v1/project/{pid}/task/{tid}/complete` | 标记完成 |
| DELETE | `/open/v1/project/{pid}/task/{tid}` | 删除任务 |

### 任务字段（create/update body 可传，response 也会带）

文档没列全，以下字段已实测官方 API 接受（来自真实任务对象 + batch_write 验证）：

- `title` (str)
- `content` (str) — 备注正文
- `desc` (str) — 描述（和 content 不是同一字段；UI 上不同位置）
- `projectId` (str) — 不传则进收件箱
- `columnId` (str) — kanban 分组 id（**官方文档未列但接受**）
- `priority` (int) — 0 无、1 低、3 中、5 高
- `dueDate` (str) — ISO 8601，如 `"2026-05-21T09:00:00.000+0000"`
- `startDate` (str) — 起始时间（可独立于 dueDate）
- `timeZone` (str) — 如 `"Asia/Shanghai"`
- `isAllDay` (bool) — 全天任务（**官方文档未列但接受**）
- `reminders` (list[str]) — 提醒规则，如 `["TRIGGER:-PT0M"]`
- `repeatFlag` (str) — RRULE，如 `"RRULE:FREQ=WEEKLY;BYDAY=MO"`（**文档未列但接受**）
- `tags` (list[str]) — 标签数组；整体替换，传空数组清空
- `items` (list[dict]) — 子任务/checklist 项，元素含 `{title, status, sortOrder, isAllDay, timeZone}`
- `kind` (str) — `"TEXT"` / `"CHECKLIST"` / `"NOTE"`；带 items 时设 `CHECKLIST`
- `sortOrder` (int) — 拖动排序
- `status` (int) — 0 未完成、2 已完成
- `etag` / `modifiedTime` — 只读

### 清单字段

- `name`, `color`, `viewMode`（`list` / `kanban` / `timeline`）
- `kind` — `TASK` / `NOTE`
- `groupId` — 清单可挂到「清单组」下（**官方 API 未暴露清单组的 CRUD**，只能通过私有 API 管理）
- `sortOrder`, `closed`

### OAuth

| 端点 | 用途 |
|---|---|
| `https://dida365.com/oauth/authorize` | 用户授权页 |
| `https://dida365.com/oauth/token` | 换 access_token（form body + Basic Auth header） |

Scope：`tasks:read tasks:write`，token 有效期约 180 天。

---

## 私有 API（Cookie 鉴权）

**仅供个人使用，非公开，随时可能变。**

必加 headers：

```
Cookie: t=<cookie_t>
User-Agent: <浏览器 UA>
Origin: https://dida365.com
Referer: https://dida365.com/webapp
x-device: {"platform":"web","os":"OS X","device":"Chrome 120",...}
x-tz: Asia/Shanghai
hl: zh_CN
```

缺 `x-device` 等会返回 500 `access_forbidden`。

### 全量同步

| 端点 | 返回 |
|---|---|
| `GET /api/v2/batch/check/0` | 全量：projectProfiles、projectGroups、syncTaskBean（update[] 即所有未完成任务）、tags、filters、habits |

### 标签 / 清单组 / 跨清单视图（衍生）

私有 API 的 `/batch/check/0` 是这些能力的唯一来源：

- **`tags[]`** — 账号所有标签，含 `{name, color, parent, sortOrder}`；滴答用 `/` 表示层级（如 `12wy/a` 的 parent 是 `12wy`）
- **`projectGroups[]`** — 清单组（侧栏文件夹），含 `{id, name, sortOrder}`
- **`syncTaskBean.update[]`** — 所有未完成任务的完整列表（含 tags、columnId、dueDate 等），用于跨清单视图（today / upcoming / by-tag）

CLI 中 `read today`、`read upcoming`、`read by-tag`、`read list-tags` 均基于这个端点实现。

### 已完成任务

| 端点 | 参数 |
|---|---|
| `GET /api/v2/project/all/completedInAll` | `from=YYYY-MM-DD%20HH:MM:SS&to=...&limit=200` |

### 番茄/专注

| 端点 | 返回 |
|---|---|
| `GET /api/v2/pomodoros/timeline?to={ts_ms}` | 每段专注详情 |
| `GET /api/v2/pomodoros/statistics/heatmap/{YYYYMMDD}/{YYYYMMDD}` | 每天专注总分钟数 |
| `GET /api/v2/pomodoros/statistics/dist/{YYYYMMDD}/{YYYYMMDD}` | 按 project/tag/task 分布 |
| `GET /api/v2/pomodoros/statistics/general` | 全时段 `{count, duration}` |

### Timeline 项字段

- `type` — 0 番茄钟模式 / 1 正向计时
- `status` — 1 已完成
- `startTime` / `endTime` — UTC ISO
- `pauseDuration` — 暂停秒数
- `tasks[]` — 关联任务

### 任务对象上的专注字段（坑）

- `focusSummaries[].pomoCount` — **是预估番茄数，不是已完成**
- `focusSummaries[].focuses[]` — `[focusId, startSec, endSec]`，差值是实际秒数
- 真实"已完成番茄数"要走 timeline / statistics

---

## 常见错误码

| 状态 | 含义 | 处理 |
|---|---|---|
| 401 (官方) | OAuth token 过期 | `refresh-token` |
| 500 access_forbidden (私有) | Cookie 失效或 headers 不全 | `refresh-cookie` |
| 500 exceed_query_limit (官方) | 触发限流（见下） | 等满 60 秒，**不要立即重试** |
| 404 (官方) | 资源不存在 | 检查 id |
| 500 unknown_exception (私有) | 通常是参数不支持 | 看响应详情 |

---

## 限流（重要）

### 官方 API

| 项 | 值 |
|---|---|
| 限制 | **100 requests / minute** |
| 计量窗口 | 滚动 60 秒 |
| 计量对象 | `access_token`（不是 IP） |
| 触发响应 | HTTP **500** + `errorCode: exceed_query_limit`（注意不是标准的 429） |
| 冷却 | 等满 60 秒（滚动窗口，少等会刷新计数） |

**1 个 CLI 子命令 ≈ 1 次官方 API 调用**，例外：

- `update-task` / `complete-task` / `delete-task` / `add-subtask` / `complete-subtask` 内部会先调 `_find_project_id_of_task`，**最坏遍历所有清单**（N+1 次调用）—— 这是大批量操作最容易爆限流的隐藏成本
- `read list-tasks` 不论清单里多少任务都是 1 次调用
- `read today` / `upcoming` / `by-tag` / `list-tags` 走私有 API，**不计入官方限流**

**批量写入实操：**

- 单条 sleep 1s，可稳定跑 ~50/min
- 超过 50 条，每 20 条歇 30 秒
- 触发限流后等满 60 秒再继续，不要 30 秒就重试

### 私有 API

无公开限流文档。实测比官方宽松，正常使用不会触发。
