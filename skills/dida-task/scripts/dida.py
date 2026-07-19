#!/usr/bin/env python3
"""dida-task 主 CLI。

用法：
    python3 dida.py <子命令> [选项]

子命令组：
    read    读取任务/清单
    pomo    番茄/专注统计
    write   写入（创建/更新/完成/删除）
    setup   首次配置
    refresh-token / refresh-cookie / health
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib import (  # noqa: E402
    CRED_FILE,
    load_credentials,
    save_credentials,
    require,
    official,
    private,
    die,
    out,
)

BJ_TZ = timezone(timedelta(hours=8))


def _to_bj(ts):
    """私有 API 返回的时间戳是 UTC（无时区标记），转成北京时间 datetime。失败返回 None。"""
    if not ts:
        return None
    try:
        return datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=timezone.utc
        ).astimezone(BJ_TZ)
    except ValueError:
        return None


def _bj_time(ts):
    dt = _to_bj(ts)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else (ts or "")[:19]


def _bj_date(ts):
    dt = _to_bj(ts)
    return dt.strftime("%Y-%m-%d") if dt else ""


# ============ READ ============
def cmd_read_list_projects(args, cred):
    require(cred, "access_token")
    projects = official("GET", "/project", cred["access_token"])
    if args.json:
        out(projects, json_mode=True)
        return
    print(f"共 {len(projects)} 个清单:")
    for p in projects:
        print(f"  {p['id']}  {p.get('name')}  (color={p.get('color') or '-'})")


def cmd_read_list_tasks(args, cred):
    require(cred, "access_token")
    pid = _resolve_project_id(cred, args.project)
    data = official("GET", f"/project/{pid}/data", cred["access_token"])
    tasks = data.get("tasks", [])
    if args.json:
        out(tasks, json_mode=True)
        return
    print(f"清单 [{data.get('project', {}).get('name')}] 未完成任务 {len(tasks)} 个:")
    for t in tasks:
        prio = {0: " ", 1: "↓", 3: "→", 5: "↑"}.get(t.get("priority", 0), "?")
        print(f"  [{prio}] {t['id']}  {t.get('title')}")


def cmd_read_list_columns(args, cred):
    require(cred, "access_token")
    pid = _resolve_project_id(cred, args.project)
    data = official("GET", f"/project/{pid}/data", cred["access_token"])
    cols = data.get("columns", []) or []
    if args.json:
        out(cols, json_mode=True)
        return
    pname = data.get("project", {}).get("name")
    vmode = data.get("project", {}).get("viewMode")
    print(f"清单 [{pname}] viewMode={vmode}  分组 {len(cols)} 个:")
    for c in cols:
        print(f"  {c['id']}  {c.get('name')}")


def cmd_read_get_task(args, cred):
    require(cred, "access_token")
    # 任务详情需要 projectId，先全量搜
    tid = args.task_id
    project_id = args.project_id or _find_project_id_of_task(cred, tid)
    if not project_id:
        die(f"找不到任务 {tid} 所属清单，请用 --project-id 指定")
    task = official("GET", f"/project/{project_id}/task/{tid}", cred["access_token"])
    out(task, json_mode=args.json)


def cmd_read_search(args, cred):
    require(cred, "cookie_t")
    data = private("GET", "/batch/check/0", cred["cookie_t"])
    tasks = data.get("syncTaskBean", {}).get("update", [])
    kw = args.keyword.lower()
    matches = [t for t in tasks if kw in (t.get("title") or "").lower()
               or kw in (t.get("content") or "").lower()]
    if args.json:
        out(matches, json_mode=True)
        return
    print(f"匹配 '{args.keyword}' 的任务 {len(matches)} 个:")
    for t in matches:
        status = "✅" if t.get("status") == 2 else "○"
        print(f"  {status} {t['id']}  {t.get('title')}  (project={t.get('projectId')})")


def _all_uncompleted_tasks(cred):
    """从私有 API 一次拿全部未完成任务。"""
    require(cred, "cookie_t")
    data = private("GET", "/batch/check/0", cred["cookie_t"])
    return data.get("syncTaskBean", {}).get("update", [])


def _all_tags(cred):
    require(cred, "cookie_t")
    data = private("GET", "/batch/check/0", cred["cookie_t"])
    return data.get("tags", []) or []


def _project_name_map(cred):
    require(cred, "access_token")
    projects = official("GET", "/project", cred["access_token"])
    pmap = {p["id"]: p["name"] for p in projects}
    pmap[None] = "📥 收件箱"
    pmap[""] = "📥 收件箱"
    return pmap


def _due_in_range(task, start_bj, end_bj):
    """task 的 dueDate 是否落在 [start, end] (北京时区) 之间。"""
    due = task.get("dueDate")
    if not due:
        return False
    try:
        dt = datetime.strptime(due[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return False
    bj = dt.astimezone(BJ_TZ)
    return start_bj <= bj <= end_bj


def _print_grouped_tasks(tasks, pmap, header):
    print(f"# {header}（{len(tasks)} 个）\n")
    def pname(pid):
        if pid in pmap:
            return pmap[pid]
        if pid and str(pid).startswith("inbox"):
            return "📥 收件箱"
        return f"未知清单({pid})"
    groups = defaultdict(list)
    for t in tasks:
        groups[pname(t.get("projectId"))].append(t)
    for pname, items in groups.items():
        print(f"## {pname} ({len(items)})")
        items.sort(key=lambda x: (x.get("dueDate") or "", -x.get("priority", 0)))
        for t in items:
            prio = {0: " ", 1: "↓", 3: "→", 5: "↑"}.get(t.get("priority", 0), "?")
            due = t.get("dueDate") or ""
            hm = ""
            if due:
                try:
                    dt = datetime.strptime(due[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                    hm = dt.astimezone(BJ_TZ).strftime(" %m-%d %H:%M")
                except Exception:
                    pass
            tags = t.get("tags") or []
            tag_str = " " + " ".join(f"#{x}" for x in tags) if tags else ""
            print(f"  [{prio}]{hm} {t.get('title')}{tag_str}  ({t['id']})")
        print()


def cmd_read_today(args, cred):
    now = datetime.now(BJ_TZ)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1, microseconds=-1)
    tasks = [t for t in _all_uncompleted_tasks(cred) if _due_in_range(t, start, end)]
    if args.json:
        out(tasks, json_mode=True)
        return
    pmap = _project_name_map(cred)
    _print_grouped_tasks(tasks, pmap, f"今日 {start.strftime('%Y-%m-%d')} 到期")


def cmd_read_upcoming(args, cred):
    now = datetime.now(BJ_TZ)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=args.days, microseconds=-1)
    tasks = [t for t in _all_uncompleted_tasks(cred) if _due_in_range(t, start, end)]
    if args.json:
        out(tasks, json_mode=True)
        return
    pmap = _project_name_map(cred)
    _print_grouped_tasks(tasks, pmap, f"未来 {args.days} 天到期")


def cmd_read_by_tag(args, cred):
    tag = args.tag.lower()
    tasks = [t for t in _all_uncompleted_tasks(cred)
             if any(tag == (x or "").lower() or (args.prefix and (x or "").lower().startswith(tag))
                    for x in (t.get("tags") or []))]
    if args.json:
        out(tasks, json_mode=True)
        return
    pmap = _project_name_map(cred)
    label = f"标签 #{args.tag}" + ("（含子标签）" if args.prefix else "")
    _print_grouped_tasks(tasks, pmap, label)


def cmd_read_list_tags(args, cred):
    tags = _all_tags(cred)
    if args.json:
        out(tags, json_mode=True)
        return
    print(f"共 {len(tags)} 个标签:")
    # 滴答 tag 用 / 分层（你的 12wy/a 12wy/loop ...）
    for t in sorted(tags, key=lambda x: x.get("name", "")):
        name = t.get("name", "?")
        parent = t.get("parent")
        color = t.get("color", "")
        suffix = f"  parent={parent}" if parent else ""
        print(f"  #{name}{suffix}  {color}")


def cmd_read_completed_today(args, cred):
    args.from_date = datetime.now(BJ_TZ).strftime("%Y-%m-%d")
    args.to_date = args.from_date
    cmd_read_completed_range(args, cred)


def cmd_read_completed_range(args, cred):
    require(cred, "cookie_t", "access_token")
    frm = urllib.parse.quote(f"{args.from_date} 00:00:00")
    to = urllib.parse.quote(f"{args.to_date} 23:59:59")
    tasks = private(
        "GET",
        f"/project/all/completedInAll?from={frm}&to={to}&limit={args.limit}",
        cred["cookie_t"],
    )
    if args.json:
        out(tasks, json_mode=True)
        return
    # 加项目名映射
    projects = official("GET", "/project", cred["access_token"])
    pmap = {p["id"]: p["name"] for p in projects}
    pmap["inbox"] = "📥 收件箱"

    groups = defaultdict(list)
    for t in tasks:
        groups[pmap.get(t.get("projectId") or "inbox", "未知")].append(t)

    print(f"# {args.from_date} ~ {args.to_date} 完成 {len(tasks)} 个任务\n")
    for pname, items in groups.items():
        print(f"## {pname} ({len(items)})")
        items.sort(key=lambda x: x.get("completedTime", ""))
        for t in items:
            ct = t.get("completedTime", "")
            hm = "??:??"
            if ct:
                try:
                    dt = datetime.strptime(ct[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                    hm = dt.astimezone(BJ_TZ).strftime("%m-%d %H:%M")
                except Exception:
                    pass
            print(f"  - [{hm}] {t.get('title')}")
        print()


# ============ POMO ============
def cmd_pomo_today(args, cred):
    require(cred, "cookie_t")
    today = datetime.now(BJ_TZ).strftime("%Y%m%d")
    heat = private("GET", f"/pomodoros/statistics/heatmap/{today}/{today}", cred["cookie_t"])
    timeline = private(
        "GET",
        f"/pomodoros/timeline?to={int(datetime.now().timestamp()*1000)}",
        cred["cookie_t"],
    )
    today_bj = datetime.now(BJ_TZ).strftime("%Y-%m-%d")
    today_sessions = [s for s in timeline if _bj_date(s.get("startTime", "")) == today_bj]
    duration = heat[0]["duration"] if heat else 0
    summary = {
        "date": today,
        "total_minutes": duration,
        "session_count": len(today_sessions),
        "sessions": today_sessions,
    }
    if args.json:
        out(summary, json_mode=True)
        return
    print(f"# {today} 专注统计")
    print(f"总时长: {duration} 分钟（约 {duration // 25} 个标准番茄）")
    print(f"段数: {len(today_sessions)}")
    print()
    for s in today_sessions:
        st = _bj_time(s.get("startTime", ""))
        et = _bj_time(s.get("endTime", ""))
        type_str = "番茄" if s.get("type") == 0 else "正向计时"
        tasks_str = ", ".join(t.get("title", "?") for t in s.get("tasks", []))
        print(f"  [{type_str}] {st} → {et}  {tasks_str}")


def cmd_pomo_by_task(args, cred):
    require(cred, "cookie_t")
    today_str = datetime.now(BJ_TZ).strftime("%Y%m%d")
    from_str = args.from_date.replace("-", "") if args.from_date else today_str
    to_str = args.to_date.replace("-", "") if args.to_date else today_str
    dist = private(
        "GET",
        f"/pomodoros/statistics/dist/{from_str}/{to_str}",
        cred["cookie_t"],
    )
    task_durs = dist.get("taskDurations", {})
    # 模糊匹配
    kw = args.task.lower()
    matches = {k: v for k, v in task_durs.items() if kw in k.lower()}
    if args.json:
        out({"range": f"{from_str}-{to_str}", "matches": matches}, json_mode=True)
        return
    if not matches:
        print(f"在 {from_str}~{to_str} 范围内没找到匹配 '{args.task}' 的任务专注记录")
        return
    print(f"# '{args.task}' 在 {from_str}~{to_str} 的专注时长")
    for name, minutes in sorted(matches.items(), key=lambda x: -x[1]):
        print(f"  - {name}: {minutes} 分钟（约 {minutes // 25} 番茄）")


def cmd_pomo_stats(args, cred):
    require(cred, "cookie_t")
    frm = args.from_date.replace("-", "")
    to = args.to_date.replace("-", "")
    heat = private("GET", f"/pomodoros/statistics/heatmap/{frm}/{to}", cred["cookie_t"])
    dist = private("GET", f"/pomodoros/statistics/dist/{frm}/{to}", cred["cookie_t"])
    general = private("GET", "/pomodoros/statistics/general", cred["cookie_t"])
    result = {
        "range": f"{frm}-{to}",
        "daily_heatmap": heat,
        "by_project": dist.get("projectDurations", {}),
        "by_tag": dist.get("tagDurations", {}),
        "by_task": dist.get("taskDurations", {}),
        "all_time_total": general,
    }
    if args.json:
        out(result, json_mode=True)
        return
    total = sum(d["duration"] for d in heat)
    print(f"# {frm}~{to} 专注统计")
    print(f"区间总时长: {total} 分钟")
    print(f"\n按项目:")
    for k, v in sorted(dist.get("projectDurations", {}).items(), key=lambda x: -x[1]):
        print(f"  {k}: {v} 分钟")
    print(f"\n按任务 (top 10):")
    top = sorted(dist.get("taskDurations", {}).items(), key=lambda x: -x[1])[:10]
    for k, v in top:
        print(f"  {k}: {v} 分钟")
    print(f"\n全时段累计: {general.get('count')} 次专注, {general.get('duration')} 分钟")


# ============ WRITE ============
def cmd_write_create_task(args, cred):
    require(cred, "access_token")
    body = {"title": args.title}
    if args.content:
        body["content"] = args.content
    if args.project:
        body["projectId"] = _resolve_project_id(cred, args.project)
    if args.priority is not None:
        body["priority"] = args.priority
    if args.due:
        body["dueDate"] = _parse_due(args.due)
    if args.repeat:
        body["repeatFlag"] = args.repeat
    if args.column:
        body["columnId"] = _resolve_column_id(cred, body.get("projectId"), args.column)
    if args.all_day:
        body["isAllDay"] = True
    if args.tags:
        body["tags"] = [t.strip() for t in args.tags.split(",") if t.strip()]
    if args.items:
        body["items"] = [{"title": s.strip(), "status": 0}
                         for s in args.items.split("|") if s.strip()]
        body["kind"] = "CHECKLIST"
    task = official("POST", "/task", cred["access_token"], body)
    if args.json:
        out(task, json_mode=True)
    else:
        print(f"✅ 任务已创建: {task['id']}  {task['title']}")


def cmd_write_update_task(args, cred):
    require(cred, "access_token")
    cur_pid = _find_project_id_of_task(cred, args.task_id)
    if not cur_pid:
        die(f"找不到任务 {args.task_id}")
    # --project 用来把任务移动到另一个清单；不传则保持原清单
    pid = _resolve_project_id(cred, args.project) if args.project else cur_pid
    body = {"id": args.task_id, "projectId": pid}
    if args.title:
        body["title"] = args.title
    if args.content:
        body["content"] = args.content
    if args.priority is not None:
        body["priority"] = args.priority
    if args.due:
        body["dueDate"] = _parse_due(args.due)
    if args.repeat:
        body["repeatFlag"] = args.repeat
    if args.column:
        body["columnId"] = _resolve_column_id(cred, pid, args.column)
    if args.all_day:
        body["isAllDay"] = True
    if args.tags is not None:
        body["tags"] = [t.strip() for t in args.tags.split(",") if t.strip()]
    task = official("POST", f"/task/{args.task_id}", cred["access_token"], body)
    out(task if args.json else f"✅ 任务已更新: {args.task_id}", json_mode=args.json)


def cmd_write_complete_task(args, cred):
    require(cred, "access_token")
    pid = _find_project_id_of_task(cred, args.task_id)
    if not pid:
        die(f"找不到任务 {args.task_id}")
    official("POST", f"/project/{pid}/task/{args.task_id}/complete", cred["access_token"])
    print(f"✅ 任务已完成: {args.task_id}")


def cmd_write_delete_task(args, cred):
    require(cred, "access_token")
    pid = _find_project_id_of_task(cred, args.task_id)
    if not pid:
        die(f"找不到任务 {args.task_id}")
    if not args.confirm:
        print(f"[DRY-RUN] 将删除任务 {args.task_id}（project {pid}）。加 --confirm 真删。")
        return
    official("DELETE", f"/project/{pid}/task/{args.task_id}", cred["access_token"])
    print(f"🗑  任务已删除: {args.task_id}")


def _load_task(cred, task_id):
    pid = _find_project_id_of_task(cred, task_id)
    if not pid:
        die(f"找不到任务 {task_id}")
    return pid, official("GET", f"/project/{pid}/task/{task_id}", cred["access_token"])


def cmd_write_add_subtask(args, cred):
    require(cred, "access_token")
    pid, task = _load_task(cred, args.task_id)
    items = task.get("items") or []
    items.append({"title": args.title, "status": 0})
    body = {"id": args.task_id, "projectId": pid, "items": items, "kind": "CHECKLIST"}
    t = official("POST", f"/task/{args.task_id}", cred["access_token"], body)
    out(t if args.json else f"✅ 已添加子任务到 {args.task_id}: {args.title}", json_mode=args.json)


def cmd_write_complete_subtask(args, cred):
    require(cred, "access_token")
    pid, task = _load_task(cred, args.task_id)
    items = task.get("items") or []
    matched = None
    kw = args.subtask.lower()
    for it in items:
        if it.get("id") == args.subtask or kw in (it.get("title") or "").lower():
            it["status"] = 2
            it["completedTime"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")
            matched = it
            break
    if not matched:
        die(f"任务 {args.task_id} 下找不到子任务: {args.subtask}（可用: {[i.get('title') for i in items]}）")
    body = {"id": args.task_id, "projectId": pid, "items": items}
    t = official("POST", f"/task/{args.task_id}", cred["access_token"], body)
    out(t if args.json else f"✅ 子任务已完成: {matched.get('title')}", json_mode=args.json)


def cmd_write_create_project(args, cred):
    require(cred, "access_token")
    body = {"name": args.name}
    if args.color:
        body["color"] = args.color
    if args.view_mode:
        body["viewMode"] = args.view_mode
    proj = official("POST", "/project", cred["access_token"], body)
    out(proj if args.json else f"✅ 清单已创建: {proj['id']}  {proj['name']}", json_mode=args.json)


def cmd_write_update_project(args, cred):
    require(cred, "access_token")
    body = {"id": args.project_id}
    if args.name:
        body["name"] = args.name
    if args.color:
        body["color"] = args.color
    proj = official("POST", f"/project/{args.project_id}", cred["access_token"], body)
    out(proj if args.json else f"✅ 清单已更新: {args.project_id}", json_mode=args.json)


def cmd_write_delete_project(args, cred):
    require(cred, "access_token")
    if not args.confirm:
        print(f"[DRY-RUN] 将删除清单 {args.project_id}。加 --confirm 真删。")
        return
    official("DELETE", f"/project/{args.project_id}", cred["access_token"])
    print(f"🗑  清单已删除: {args.project_id}")


# ============ META ============
def cmd_setup(args, cred):
    print("=== Dida-Task 首次配置 ===\n")
    print("第一步：去 https://developer.dida365.com/ 注册应用，拿到 Client ID 和 Client Secret")
    print("       OAuth Redirect URL 填 http://localhost:8080/callback\n")
    client_id = input("Client ID: ").strip()
    client_secret = input("Client Secret: ").strip()
    redirect_uri = input("Redirect URI [http://localhost:8080/callback]: ").strip() or "http://localhost:8080/callback"

    print("\n第二步：浏览器授权（拿 OAuth token，用于写操作）")
    from oauth import authorize
    token = authorize(client_id, client_secret, redirect_uri)

    print("\n第三步：拿浏览器 cookie（用于读取已完成任务和番茄统计）")
    print("⚠️  这是非官方私有 API，必须用 cookie。Cookie 会过期，过期时跑 `refresh-cookie`")
    print("    方法：浏览器登录 dida365.com → F12 → Application → Cookies → 复制 't' 的 Value")
    cookie_t = input("Cookie 't' value (留空跳过，跳过则不能读已完成任务/番茄): ").strip()

    save_credentials({
        "client_id": client_id,
        "client_secret": client_secret,
        "access_token": token,
        "redirect_uri": redirect_uri,
        "cookie_t": cookie_t,
    })
    print(f"\n✅ 凭证已保存到 {CRED_FILE}")
    print("跑 `python3 dida.py health` 检查状态。")


def cmd_refresh_token(args, cred):
    require(cred, "client_id", "client_secret", "redirect_uri")
    from oauth import authorize
    token = authorize(cred["client_id"], cred["client_secret"], cred["redirect_uri"])
    cred["access_token"] = token
    save_credentials(cred)
    print(f"✅ access_token 已更新")


def cmd_refresh_cookie(args, cred):
    print("浏览器登录 dida365.com → F12 → Application → Cookies → https://dida365.com")
    print("找到名为 't' 的 cookie，复制 Value 粘贴到这里：")
    cookie_t = input("Cookie 't': ").strip()
    if not cookie_t:
        die("未输入 cookie")
    cred["cookie_t"] = cookie_t
    save_credentials(cred)
    print("✅ cookie 已更新")


def cmd_health(args, cred):
    print(f"配置文件: {CRED_FILE} ({'存在' if CRED_FILE.exists() else '不存在'})")
    print(f"client_id: {'✅' if cred.get('client_id') else '❌'}")
    print(f"client_secret: {'✅' if cred.get('client_secret') else '❌'}")
    print(f"access_token: {'✅' if cred.get('access_token') else '❌'}")
    print(f"cookie_t: {'✅' if cred.get('cookie_t') else '❌'}")

    if cred.get("access_token"):
        try:
            projs = official("GET", "/project", cred["access_token"])
            print(f"官方 API: ✅ 可用（{len(projs)} 个清单）")
        except SystemExit:
            print(f"官方 API: ❌ token 失效，跑 refresh-token")
    if cred.get("cookie_t"):
        try:
            private("GET", "/pomodoros/statistics/general", cred["cookie_t"])
            print(f"私有 API: ✅ 可用")
        except SystemExit:
            print(f"私有 API: ❌ cookie 失效，跑 refresh-cookie")


# ============ 工具函数 ============
def _resolve_project_id(cred: dict, project: str) -> str:
    """project 可以是 id 或名字。"""
    if not project:
        return None
    projects = official("GET", "/project", cred["access_token"])
    for p in projects:
        if p["id"] == project or p["name"] == project:
            return p["id"]
    die(f"找不到清单: {project}")


def _resolve_column_id(cred: dict, project_id: str, column: str) -> str:
    """column 可以是 id 或名字。需要 project_id 才能查 columns。"""
    if not column:
        return None
    if not project_id:
        die("--column 需要同时指定 --project")
    data = official("GET", f"/project/{project_id}/data", cred["access_token"])
    cols = data.get("columns", []) or []
    for c in cols:
        if c["id"] == column or c.get("name") == column:
            return c["id"]
    die(f"清单 {project_id} 下找不到分组: {column}（可用: {[c.get('name') for c in cols]}）")


def _find_project_id_of_task(cred: dict, task_id: str) -> str:
    """在所有清单里搜任务，返回所属清单 id。"""
    if not cred.get("access_token"):
        return None
    projects = official("GET", "/project", cred["access_token"])
    for p in projects:
        data = official("GET", f"/project/{p['id']}/data", cred["access_token"])
        for t in data.get("tasks", []):
            if t["id"] == task_id:
                return p["id"]
    return None


def _parse_due(s: str) -> str:
    """支持 'YYYY-MM-DD' 或 'YYYY-MM-DDTHH:MM' 或完整 ISO。"""
    if len(s) == 10:
        return f"{s}T09:00:00.000+0000"
    if len(s) == 16:
        return f"{s}:00.000+0000"
    return s


# ============ argparse ============
def build_parser():
    p = argparse.ArgumentParser(prog="dida")
    sub = p.add_subparsers(dest="cmd", required=True)

    # read
    p_read = sub.add_parser("read", help="读取任务/清单")
    r_sub = p_read.add_subparsers(dest="rcmd", required=True)
    r_sub.add_parser("list-projects").set_defaults(func=cmd_read_list_projects)
    rt = r_sub.add_parser("list-tasks")
    rt.add_argument("project", help="清单 id 或名字")
    rt.set_defaults(func=cmd_read_list_tasks)
    rlc = r_sub.add_parser("list-columns", help="读 kanban 清单的分组")
    rlc.add_argument("project", help="清单 id 或名字")
    rlc.set_defaults(func=cmd_read_list_columns)
    rg = r_sub.add_parser("get-task")
    rg.add_argument("task_id")
    rg.add_argument("--project-id")
    rg.set_defaults(func=cmd_read_get_task)
    rs = r_sub.add_parser("search")
    rs.add_argument("keyword")
    rs.set_defaults(func=cmd_read_search)
    r_sub.add_parser("today", help="跨清单：今日到期的未完成任务").set_defaults(func=cmd_read_today)
    rup = r_sub.add_parser("upcoming", help="跨清单：未来 N 天到期")
    rup.add_argument("--days", type=int, default=7)
    rup.set_defaults(func=cmd_read_upcoming)
    rbt = r_sub.add_parser("by-tag", help="按标签筛选未完成任务")
    rbt.add_argument("tag")
    rbt.add_argument("--prefix", action="store_true", help="匹配子标签（如 12wy 含 12wy/a）")
    rbt.set_defaults(func=cmd_read_by_tag)
    r_sub.add_parser("list-tags", help="列出账号所有标签").set_defaults(func=cmd_read_list_tags)
    rct = r_sub.add_parser("completed-today")
    rct.add_argument("--limit", type=int, default=200)
    rct.set_defaults(func=cmd_read_completed_today)
    rcr = r_sub.add_parser("completed-range")
    rcr.add_argument("from_date", help="YYYY-MM-DD")
    rcr.add_argument("to_date", help="YYYY-MM-DD")
    rcr.add_argument("--limit", type=int, default=200)
    rcr.set_defaults(func=cmd_read_completed_range)
    for r in [r_sub.choices[c] for c in r_sub.choices]:
        r.add_argument("--json", action="store_true")

    # pomo
    p_pomo = sub.add_parser("pomo", help="番茄/专注统计")
    pp = p_pomo.add_subparsers(dest="pcmd", required=True)
    pp.add_parser("today").set_defaults(func=cmd_pomo_today)
    pbt = pp.add_parser("by-task")
    pbt.add_argument("task", help="任务名关键词")
    pbt.add_argument("--from", dest="from_date")
    pbt.add_argument("--to", dest="to_date")
    pbt.set_defaults(func=cmd_pomo_by_task)
    ps = pp.add_parser("stats")
    ps.add_argument("from_date", help="YYYY-MM-DD")
    ps.add_argument("to_date", help="YYYY-MM-DD")
    ps.set_defaults(func=cmd_pomo_stats)
    for r in [pp.choices[c] for c in pp.choices]:
        r.add_argument("--json", action="store_true")

    # write
    p_write = sub.add_parser("write", help="写入操作")
    w = p_write.add_subparsers(dest="wcmd", required=True)

    wct = w.add_parser("create-task")
    wct.add_argument("--title", required=True)
    wct.add_argument("--content")
    wct.add_argument("--project", help="清单 id 或名字（默认收件箱）")
    wct.add_argument("--priority", type=int, choices=[0, 1, 3, 5])
    wct.add_argument("--due", help="YYYY-MM-DD 或 YYYY-MM-DDTHH:MM")
    wct.add_argument("--repeat", help="重复规则 RRULE，如 'RRULE:FREQ=DAILY;INTERVAL=1'")
    wct.add_argument("--column", help="kanban 分组 id 或名字（需配合 --project）")
    wct.add_argument("--all-day", action="store_true", help="全天任务（忽略 due 的时分秒）")
    wct.add_argument("--tags", help="标签，逗号分隔，如 '12wy/a,work'")
    wct.add_argument("--items", help="子任务列表，竖线分隔，如 'step1|step2|step3'（自动设 kind=CHECKLIST）")
    wct.set_defaults(func=cmd_write_create_task)

    wut = w.add_parser("update-task")
    wut.add_argument("task_id")
    wut.add_argument("--project", help="目标清单 id 或名字（指定即移动到该清单）")
    wut.add_argument("--title")
    wut.add_argument("--content")
    wut.add_argument("--priority", type=int, choices=[0, 1, 3, 5])
    wut.add_argument("--due")
    wut.add_argument("--repeat", help="重复规则 RRULE，如 'RRULE:FREQ=DAILY;INTERVAL=1'")
    wut.add_argument("--column", help="kanban 分组 id 或名字")
    wut.add_argument("--all-day", action="store_true", help="全天任务")
    wut.add_argument("--tags", help="标签，逗号分隔（整体替换；传空串清空）")
    wut.set_defaults(func=cmd_write_update_task)

    wcomp = w.add_parser("complete-task")
    wcomp.add_argument("task_id")
    wcomp.set_defaults(func=cmd_write_complete_task)

    wdt = w.add_parser("delete-task")
    wdt.add_argument("task_id")
    wdt.add_argument("--confirm", action="store_true")
    wdt.set_defaults(func=cmd_write_delete_task)

    wast = w.add_parser("add-subtask")
    wast.add_argument("task_id")
    wast.add_argument("--title", required=True)
    wast.set_defaults(func=cmd_write_add_subtask)

    wcst = w.add_parser("complete-subtask")
    wcst.add_argument("task_id")
    wcst.add_argument("subtask", help="子任务 id 或标题关键词")
    wcst.set_defaults(func=cmd_write_complete_subtask)

    wcp = w.add_parser("create-project")
    wcp.add_argument("--name", required=True)
    wcp.add_argument("--color")
    wcp.add_argument("--view-mode", choices=["list", "kanban", "timeline"], default="list")
    wcp.set_defaults(func=cmd_write_create_project)

    wup = w.add_parser("update-project")
    wup.add_argument("project_id")
    wup.add_argument("--name")
    wup.add_argument("--color")
    wup.set_defaults(func=cmd_write_update_project)

    wdp = w.add_parser("delete-project")
    wdp.add_argument("project_id")
    wdp.add_argument("--confirm", action="store_true")
    wdp.set_defaults(func=cmd_write_delete_project)
    for r in [w.choices[c] for c in w.choices]:
        r.add_argument("--json", action="store_true")

    # meta
    sub.add_parser("setup").set_defaults(func=cmd_setup)
    sub.add_parser("refresh-token").set_defaults(func=cmd_refresh_token)
    sub.add_parser("refresh-cookie").set_defaults(func=cmd_refresh_cookie)
    sub.add_parser("health").set_defaults(func=cmd_health)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    # 给那些没声明 --json 的元命令补默认
    if not hasattr(args, "json"):
        args.json = False
    cred = load_credentials()
    args.func(args, cred)


if __name__ == "__main__":
    main()
