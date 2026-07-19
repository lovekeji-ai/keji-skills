# Dida-Task 使用示例

所有命令统一入口：`python3 scripts/dida.py ...`

## 首次配置

```bash
python3 scripts/dida.py setup
python3 scripts/dida.py health
```

## 读

```bash
# 我有哪些清单
python3 scripts/dida.py read list-projects

# 看"工作"清单下未完成的
python3 scripts/dida.py read list-tasks 工作

# 全量搜任务
python3 scripts/dida.py read search "周报"

# 单任务详情
python3 scripts/dida.py read get-task <task_id>

# 今天完成了哪些
python3 scripts/dida.py read completed-today

# 上周完成的（按北京时间日期）
python3 scripts/dida.py read completed-range 2026-05-14 2026-05-20
```

## 番茄/专注

```bash
# 今天专注了多久
python3 scripts/dida.py pomo today

# 某任务花了几个番茄（默认今天）
python3 scripts/dida.py pomo by-task "周报"

# 某任务在某段时间的番茄
python3 scripts/dida.py pomo by-task "周报" --from 2026-05-01 --to 2026-05-21

# 本月专注分布
python3 scripts/dida.py pomo stats 2026-05-01 2026-05-31
```

## 写

```bash
# 创建任务（默认进收件箱）
python3 scripts/dida.py write create-task --title "买牛奶"

# 高优 + 指定清单 + 截止
python3 scripts/dida.py write create-task \
  --title "写周报" --project 工作 --priority 5 --due 2026-05-22

# 带备注
python3 scripts/dida.py write create-task \
  --title "找律师" --content "问下合同模板的事"

# 更新任务
python3 scripts/dida.py write update-task <task_id> --priority 3 --due 2026-05-25

# 完成任务
python3 scripts/dida.py write complete-task <task_id>

# 删除任务（默认 dry-run）
python3 scripts/dida.py write delete-task <task_id>           # 不会真删
python3 scripts/dida.py write delete-task <task_id> --confirm # 真删

# 创建清单
python3 scripts/dida.py write create-project --name "读书笔记" --color "#4287f5"

# 删除清单
python3 scripts/dida.py write delete-project <project_id> --confirm
```

## JSON 输出（给 agent 解析用）

所有读写命令都支持 `--json`：

```bash
python3 scripts/dida.py read list-projects --json
python3 scripts/dida.py pomo today --json
python3 scripts/dida.py write create-task --title "test" --json
```

## 续期

```bash
# OAuth token 过期
python3 scripts/dida.py refresh-token

# Cookie 失效
python3 scripts/dida.py refresh-cookie

# 看哪个失效了
python3 scripts/dida.py health
```

## 优先级编码

| Priority | 含义 |
|---|---|
| 0 | 无优先级 |
| 1 | 低 ↓ |
| 3 | 中 → |
| 5 | 高 ↑ |
