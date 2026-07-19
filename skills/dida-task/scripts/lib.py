"""dida-task 共享库：凭证加载、HTTP 调用、错误处理。"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# === 端点常量 ===
OAUTH_AUTHORIZE = "https://dida365.com/oauth/authorize"
OAUTH_TOKEN = "https://dida365.com/oauth/token"
OFFICIAL_BASE = "https://api.dida365.com/open/v1"
PRIVATE_BASE = "https://api.dida365.com/api/v2"

# === 配置路径 ===
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "dida-task"
CRED_FILE = CONFIG_DIR / "credentials.json"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


# === 凭证 ===
def load_credentials() -> dict:
    """三层 fallback：环境变量 > 配置文件 > 报错引导 setup。"""
    cred = {}
    if CRED_FILE.exists():
        try:
            cred = json.loads(CRED_FILE.read_text())
        except json.JSONDecodeError:
            pass
    # 环境变量覆盖
    for k_env, k_cred in [
        ("DIDA_CLIENT_ID", "client_id"),
        ("DIDA_CLIENT_SECRET", "client_secret"),
        ("DIDA_ACCESS_TOKEN", "access_token"),
        ("DIDA_REDIRECT_URI", "redirect_uri"),
        ("DIDA_COOKIE_T", "cookie_t"),
    ]:
        v = os.environ.get(k_env)
        if v:
            cred[k_cred] = v
    return cred


def save_credentials(cred: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CRED_FILE.write_text(json.dumps(cred, indent=2, ensure_ascii=False))
    CRED_FILE.chmod(0o600)


def require(cred: dict, *keys: str) -> None:
    missing = [k for k in keys if not cred.get(k)]
    if missing:
        die(
            f"缺少凭证: {', '.join(missing)}\n"
            f"请跑 `python3 scripts/dida.py setup` 完成首次配置，"
            f"或在 ~/.zshrc / {CRED_FILE} 中提供。"
        )


# === HTTP ===
def _request(url: str, method: str, headers: dict, body: Any = None) -> tuple[int, str]:
    data = None
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode()
            headers.setdefault("Content-Type", "application/json")
        elif isinstance(body, str):
            data = body.encode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def official(method: str, path: str, token: str, body: Any = None) -> Any:
    code, text = _request(
        OFFICIAL_BASE + path,
        method,
        {"Authorization": f"Bearer {token}"},
        body,
    )
    if code == 401:
        die(
            "[官方 API] OAuth token 已失效。\n"
            "请跑 `python3 scripts/dida.py refresh-token` 重新授权。"
        )
    if code == 500 and "exceed_query_limit" in text:
        # 官方限流：100 req/min per access_token，滚动 60s 窗口，超限返回 HTTP 500（不是 429）
        die(
            "[官方 API] 触发限流（100 req/min per token）。\n"
            "等满 60 秒再重试。批量写入请每条 sleep 1s，"
            "或每 20 条歇 30 秒。**不要立即重试**（滚动窗口会被刷新）。"
        )
    if code >= 400:
        die(f"[官方 API] HTTP {code}: {text[:300]}")
    return json.loads(text) if text else None


def private(method: str, path: str, cookie_t: str, body: Any = None, query: dict = None) -> Any:
    url = PRIVATE_BASE + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    headers = {
        "Cookie": f"t={cookie_t}",
        "User-Agent": UA,
        "Origin": "https://dida365.com",
        "Referer": "https://dida365.com/webapp",
        "x-device": (
            '{"platform":"web","os":"OS X","device":"Chrome 120","name":"",'
            '"version":6070,"id":"6644f1f8aaaaaaaaaaaaaaaa","channel":"website",'
            '"campaign":"","websocket":""}'
        ),
        "x-tz": "Asia/Shanghai",
        "hl": "zh_CN",
    }
    code, text = _request(url, method, headers, body)
    if code == 500 and "access_forbidden" in text:
        die(
            "[私有 API] Cookie 已失效或被风控。\n"
            "请跑 `python3 scripts/dida.py refresh-cookie` 引导更新 cookie。"
        )
    if code == 401:
        die(
            "[私有 API] Cookie 未授权。\n"
            "请跑 `python3 scripts/dida.py refresh-cookie`。"
        )
    if code >= 400:
        die(f"[私有 API] HTTP {code}: {text[:300]}")
    return json.loads(text) if text else None


# === 工具 ===
def die(msg: str, code: int = 1) -> None:
    sys.stderr.write(msg + "\n")
    sys.exit(code)


def out(data: Any, json_mode: bool = False) -> None:
    if json_mode:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        if isinstance(data, str):
            print(data)
        else:
            print(json.dumps(data, ensure_ascii=False, indent=2))
