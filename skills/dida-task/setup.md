# Dida-Task 首次配置

## 步骤总览

1. 在滴答清单开发者平台注册一个应用，拿 Client ID / Secret
2. 跑 `python3 scripts/dida.py setup`，按引导完成 OAuth 授权 + 录入 cookie
3. 跑 `python3 scripts/dida.py health` 验证

---

## 步骤 1：注册应用

1. 打开 https://developer.dida365.com/
2. 右上角点 **Manage Apps**
3. 用你的滴答清单账号登录（同 App 账号）
4. 点 **+App Name** 创建应用，名字随便填（比如 `my-agent`）
5. 进入应用详情，会自动生成 **Client ID** 和 **Client Secret**
6. 填 **OAuth Redirect URL**：`http://localhost:8080/callback`（必须精确一致）

> ⚠️ 不要把 Client Secret 提交到 git 或截图发出去。本 skill 会把它存到 `~/.config/dida-task/credentials.json`（权限 600）。

---

## 步骤 2：跑 setup

```bash
python3 scripts/dida.py setup
```

会问你三件事：

1. **Client ID** 和 **Client Secret** —— 从步骤 1 拿
2. **OAuth 授权** —— 自动弹浏览器，点"同意"，回调自动接收
3. **Cookie 't'** —— 这是私有 API 鉴权用，**只为读已完成任务和番茄统计**

### 关于 Cookie（重要）

**为什么需要**：滴答清单官方 OpenAPI 不提供"读已完成任务"和"番茄统计"接口，只能走私有 API，用浏览器 cookie 鉴权。

**怎么拿**：
1. 浏览器登录 https://dida365.com
2. F12 打开开发者工具 → Application → Cookies → `https://dida365.com`
3. 找到名为 **`t`** 的 cookie，复制 Value（很长一串）
4. 粘贴到 setup 的提示里

**风险与限制（一定要知道）**：
- 这是**非官方 API**，滴答有权随时改动或封禁
- Cookie 有效期一般几周到几个月，过期后需要重新从浏览器复制
- 仅供个人使用，**不要用于商业产品或大规模爬取**
- 如果你只需要写任务、读未完成任务，跳过 cookie 即可

跳过 cookie 后，可用功能：
- ✅ 所有写操作（创建、更新、完成、删除任务和清单）
- ✅ 列清单、列未完成任务、读任务详情
- ❌ 读已完成任务
- ❌ 番茄/专注统计
- ❌ 全量任务搜索（这个走的也是私有 API）

---

## 步骤 3：验证

```bash
python3 scripts/dida.py health
```

预期输出：

```
配置文件: ~/.config/dida-task/credentials.json (存在)
client_id: ✅
client_secret: ✅
access_token: ✅
cookie_t: ✅
官方 API: ✅ 可用（N 个清单）
私有 API: ✅ 可用
```

---

## 凭证位置

按优先级：

1. **环境变量**（优先级最高）
   - `DIDA_CLIENT_ID`、`DIDA_CLIENT_SECRET`、`DIDA_ACCESS_TOKEN`、`DIDA_REDIRECT_URI`、`DIDA_COOKIE_T`
2. **配置文件**：`~/.config/dida-task/credentials.json`（setup 自动写入）

如果你已经在 `~/.zshrc` 里设了环境变量，setup 时也可以选择不重复保存到配置文件。

---

## 续期

### OAuth token 过期（约 180 天）
症状：写操作返回 401
解决：`python3 scripts/dida.py refresh-token`，自动重走授权

### Cookie 失效（几周-几个月不等）
症状：读已完成任务或番茄统计时报 `[私有 API] Cookie 已失效或被风控`
解决：`python3 scripts/dida.py refresh-cookie`，按提示从浏览器重新复制

### 检查状态
随时跑 `python3 scripts/dida.py health` 看哪个失效了。
