"""OAuth 授权流程：启动本地回调，引导用户浏览器授权，换 access_token。"""
from __future__ import annotations

import base64
import http.server
import json
import socketserver
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser

from lib import OAUTH_AUTHORIZE, OAUTH_TOKEN, die

SCOPE = "tasks:write tasks:read"
STATE = "dida-task-skill"

received: dict = {}


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in qs:
            received["code"] = qs["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<h1>OK</h1><p>Authorization received. You can close this tab "
                b"and go back to the terminal.</p>"
            )
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"missing 'code' in query")

    def log_message(self, *_a, **_k):
        pass


def authorize(client_id: str, client_secret: str, redirect_uri: str, port: int = 8080) -> str:
    """跑完整 OAuth flow，返回 access_token。"""
    server = socketserver.TCPServer(("localhost", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    params = {
        "client_id": client_id,
        "scope": SCOPE,
        "state": STATE,
        "redirect_uri": redirect_uri,
        "response_type": "code",
    }
    auth_url = f"{OAUTH_AUTHORIZE}?{urllib.parse.urlencode(params)}"
    print(f"\n👉 在浏览器打开授权链接并点'同意'：\n{auth_url}\n")
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass
    print(f"⏳ 等待回调（最多 5 分钟，监听 localhost:{port}）...")

    for _ in range(300):
        if "code" in received:
            break
        time.sleep(1)
    server.shutdown()

    if "code" not in received:
        die("超时未收到授权 code，请重试。")

    print("✅ 收到 code，换 access_token...")
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    body = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": received["code"],
        "grant_type": "authorization_code",
        "scope": SCOPE,
        "redirect_uri": redirect_uri,
    }).encode()
    req = urllib.request.Request(
        OAUTH_TOKEN,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {basic}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.loads(r.read())

    token = resp.get("access_token")
    if not token:
        die(f"token 换取失败: {resp}")
    expires_days = resp.get("expires_in", 0) // 86400
    print(f"✅ access_token 已拿到（有效期约 {expires_days} 天）")
    return token


if __name__ == "__main__":
    # 独立测试入口
    if len(sys.argv) < 4:
        die("用法: python3 oauth.py <client_id> <client_secret> <redirect_uri>")
    print(authorize(sys.argv[1], sys.argv[2], sys.argv[3]))
