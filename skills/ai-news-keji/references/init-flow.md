# 初始化分步向导细则

`SKILL.md` 中的"分步初始化"只保留契约：每一步先用一句话说明这一步的作用，**然后必须调用 `AskUserQuestion`**。每步的选项与文案细节见下，`scripts/init_wizard.py` 输出与本文件保持一致；如二者冲突以脚本输出为准。

## 共同要求

- 每轮只处理当前步骤；用户作答后才推进。
- 选项里若需要"自定义"，使用 `AskUserQuestion` 的"其他"自由文本字段。
- 单行字段才用"其他"；多行画像见第 4 步。

## 第 1 步 — 外部集成

- `multiSelect: true`
- 选项：`follow-builders`、`BestBlogs`、`ak-rss-digest`、`暂不安装`
- 已检测到本机已安装的集成，label 追加"（本条已安装）"，仍默认列出供用户保留
- 说明文案：扩大 AI builder、技术博客和 RSS 覆盖；本轮只收集这个答案

## 第 2 步 — Newsletter 来源

- 先读取 `sources.yaml`（缺则 `sources.example.yaml`），在说明里展示 Newsletter 名称、订阅地址、发件人白名单
- 单选选项：
  - `imap（现在配置 IMAP 接入）`
  - `later（先跳过，稍后再配）`
  - `no（不接入邮件来源）`

### 第 2.1 步 — IMAP 配置（仅当上一步选 `imap`）

用 **一次** `AskUserQuestion` 调用收集 4 个字段，每个字段给常见预设：

| 字段 | 预设选项 |
| --- | --- |
| IMAP host | `imap.gmail.com`、`imap.qq.com`、`imap.163.com`、`outlook.office365.com` |
| folder | `INBOX` |
| 账号环境变量名 | `AI_NEWS_IMAP_USERNAME` |
| 密码/授权码环境变量名 | `AI_NEWS_IMAP_PASSWORD` |

说明里再次提醒：账号和密码只通过环境变量提供，**绝不写入** `config.yaml`。

## 第 3 步 — 输出目录

- 单选；选项：`~/ai-news-keji/output`（默认）、`~/Documents/ai-news-keji`，并允许"其他"自定义路径

## 第 4 步 — 个人偏好

- 单选预置画像：`工程 + AI 产品方向`、`研究 + 论文方向`、`创业 + 投资方向`、`暂不填写，使用默认`
- 说明里提醒这一步会影响评分和摘要重点
- **多行画像处理**：如果用户选"其他"想填写完整的多行偏好描述，**结束本轮 `AskUserQuestion`**，下一轮改用普通对话邀请用户粘贴一段画像文本，再写入 `paths.filter_rules` 指向的文件

## 收尾

- 收集完全部答案后写入临时 JSON，运行 `python3 scripts/init.py --answers-file <answers.json>`
- JSON 字段：`external_skills`、`newsletter.choice`、`newsletter.host`、`newsletter.folder`、`newsletter.username_env`、`newsletter.password_env`、`output_dir`、`preferences`
- 写入后再次 `python3 scripts/init.py --check`，通过后才进入抓取流程
