# keji-skills

> 柯基的 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 个人 Skill 作品集。

一个 monorepo，装着柯基日常在用的 Skill —— 每个都是一个开箱即用的 Agent 工作流。可以整包安装成 Claude Code 插件市场，也可以只挑单个 Skill 用。

## 安装

### 方式一：作为 Claude Code 插件市场安装（推荐）

```bash
/plugin marketplace add lovekeji-ai/keji-skills
/plugin install keji-skills@keji-skills
```

安装后所有 Skill 自动出现在 `/` 命令列表里。

### 方式二：只挑单个 Skill

```bash
git clone https://github.com/lovekeji-ai/keji-skills.git
ln -s "$PWD/keji-skills/skills/ai-news-keji" ~/.claude/skills/ai-news-keji
```

## Skill 清单

| Skill | 一句话说明 |
|-------|-----------|
| [**ai-news-keji**](skills/ai-news-keji/) | AI / 科技新闻日报 —— Newsletter + RSS + AI HOT 等多源自动抓取、跨源去重、按兴趣评分，生成 Obsidian 友好的每日 Markdown 摘要 |

*更多 Skill 陆续加入中。*

## 目录结构

```
keji-skills/
├── .claude-plugin/         # Claude Code 插件市场清单
│   ├── marketplace.json
│   └── plugin.json
├── skills/                 # 每个子目录一个 Skill
│   └── ai-news-keji/
│       └── SKILL.md
└── README.md
```

## License

[MIT](LICENSE)
