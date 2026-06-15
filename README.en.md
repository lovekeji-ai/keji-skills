[中文](README.md) | **English**

# ai-news-keji

> An AI / tech news digest skill. Let high-quality sources do the first pass of filtering, then let your agent dedupe across sources, score against your interests, and deliver a daily Markdown brief ready to drop into Obsidian.

This isn't another feed reader — it's the skeleton for a personal intelligence system that brings information to you. No more opening AI HOT, five Newsletter sites, scrolling X, and flipping through an RSS reader every morning. Just say "generate today's AI digest" in your agent and the rest is taken care of.

## What you get

Two Markdown files per day, written to your chosen output directory (default `~/ai-news-keji/output`):

```text
2026-04-25.md          # Raw brief: one section per source, organized by time and category
2026-04-25 摘要.md     # Summary: dual-track ("industry radar" + "personal value")
```

The summary follows [prompts/summary-template.md](prompts/summary-template.md) and includes:

- Today's industry-defining events
- What's useful for you today
- Worth watching
- Key signals of the day

A rolling event log is maintained across days so continuation coverage of stories you've already seen gets demoted instead of repeatedly clogging your feed.

## Design: three-layer filtering

```text
Heavy aggregators
AI HOT / BestBlogs / 量子位 / Readwise — pulling from across the web
        ↓
Editor-curated layer
TLDR / The Rundown AI / Ben's Bites / The Neuron — second-pass curation
        ↓
Independent voices
Latent.Space / DeepLearning.AI / personal Newsletters — irreplaceable judgment
        ↓
Your daily brief
Cross-source dedup, interest-weighted scoring, written to Markdown
```

The defaults lean AI / tech, but intentionally keep room for engineering, startup, creator-economy, design, and cross-disciplinary thinking — so the digest doesn't degenerate into homogenized AI hype.

## Quick Start

1. Register this skill into your agent (Claude Code or Codex — commands at the bottom)
2. In your agent, say `/ai-news-keji` or "generate today's AI digest"
3. **The first run triggers a conversational onboarding** — the agent pops up `AskUserQuestion` cards for four steps. Click through; no YAML to edit.

AI HOT is already wired in as a default source. It needs no API key, login, or extra install; the "external integrations" onboarding question is only for optional add-ons like `follow-builders`, `BestBlogs`, and `ak-rss-digest`.

After setup, one sentence is all you need to produce the daily brief. You don't open a config file, you don't memorize commands.

## What happens on first run

When the agent detects an uninitialized environment, it walks you through the setup with `AskUserQuestion` (every step accepts an "Other" free-form answer):

| Step | Question |
| --- | --- |
| 1. External integrations | Enable any of `follow-builders` / `BestBlogs` / `ak-rss-digest`? (multi-select; already-installed ones are auto-detected and labeled) |
| 2. Newsletter access | `IMAP` (any standard mailbox) / `MCP` (agent runtime with a Gmail MCP server) / later / no |
| 2.1 IMAP credentials | Only when IMAP is selected: host, folder, env var names for username / password (credentials live only in env vars, never in config files) |
| 3. Output directory | Default `~/ai-news-keji/output`, or pick your own |
| 4. Personal profile | Engineering / research / startup / custom — written into a local `filter-rules.md` to weight scoring and summarization |

If you enable BestBlogs, the agent additionally checks whether `bestblogs` is logged in. If not, it prompts you to grab an API key at [bestblogs.dev/settings](https://bestblogs.dev/settings) and runs `bestblogs auth login` interactively.

## Daily usage

```text
generate today's AI digest
generate the digest for 2026-04-25
refresh today's digest
/ai-news-keji
```

If artifacts already exist for that date, the agent asks you to choose between:

- **Use existing results** — just hand back the paths
- **Incremental fetch** — keep what you have, append new entries from currently available sources, regenerate the summary
- **Full re-fetch and overwrite** — clear the cache and rebuild (this overwrites whatever you'd already read, so it's confirmed before running)

## Changing things later — just ask

Every setting is reachable through conversation; **you never have to touch a config file**:

- "Reconfigure Newsletter" / "switch to MCP for Newsletter"
- "Move the output to ~/Documents/ai-news-keji"
- "Reselect external integrations"
- "Update my profile — focus more on agent frameworks and engineering practice"
- "Make the summary shorter"

The agent re-pops the relevant step's option card; everything else stays put.

## Default sources

AI HOT is enabled by default in the public config. RSS, Newsletter, External Skill, and Website sources live in [`sources.example.yaml`](sources.example.yaml) — drop or extend them as you like. AI HOT is not configured in `sources.yaml`; it is a built-in API source fetched by `scripts/fetch-aihot.py`, including pagination and date filtering.

| Type | Default entries | Purpose |
| --- | --- | --- |
| API | AI HOT | Chinese AI trend curation; anonymous REST API, no token required |
| RSS | 量子位, 三花 AI 快讯 | Chinese AI media as a baseline |
| Newsletter | TLDR (AI / Dev / Founders), The Rundown AI, The Neuron, AI Breakfast, AI Valley, Ben's Bites | Editor-curated layer — "what mattered today" |
| External Skill / CLI | follow-builders, BestBlogs, ak-rss-digest | X, podcasts, independent blogs |
| Website | Readwise Weekly | Long-form discovery via reader-highlight signals |

Each source can set its own `frequency`:

| frequency | Behavior |
| --- | --- |
| `daily` | Always check |
| `weekday` | Skip on weekends |
| `3x_week` | Always check; empty days are fine |
| `weekly` | Skip if it's been fetched successfully in the last week |
| `irregular` | Always check; empty days are fine |

Want to add a source? Tell the agent ("add Stratechery as a Newsletter") or edit `sources.yaml` — both work.

## Newsletter access: IMAP vs MCP

Newsletters are the highest-signal layer in the digest, but reading them needs credentials. Two options:

| | IMAP | MCP |
| --- | --- | --- |
| Mailboxes | Any standard mailbox (Gmail / iCloud / Outlook / QQ / 163…) | Depends on the MCP server — currently mostly Gmail / Workspace |
| Credentials | App password / auth code, stored in local env vars | OAuth, managed by the MCP server; this repo stores nothing |
| Debuggability | Short loop, can be verified end-to-end | MCP server is a black box; debugging means reading runtime logs |
| Runtime | Any Python environment | Must run inside an agent runtime that has the MCP server registered |

**Rule of thumb**: default to IMAP; only pick MCP if you already use a Gmail MCP server.

The agent asks you which one in step 2 of onboarding; you can switch later by saying "switch Newsletter to MCP."

## Three optional integrations

These are off by default. The agent asks about them in step 1:

| Name | What it does | Notes |
| --- | --- | --- |
| [follow-builders](https://github.com/zarazhangrui/follow-builders) | Tracks top AI builders' X posts, podcasts, and official blogs | Git-form skill |
| [BestBlogs](https://github.com/ginobefun/bestblogs) | Curated technical / AI / product deep-reads | npm CLI; **`bestblogs auth login` is required** — without it the source returns nothing |
| [ak-rss-digest](https://github.com/rookie-ricardo/erduo-skills) | Large independent-blog RSS pool with AI scoring + summaries | Git-form skill |

Skipping all three still works — you just lose those signal sources.

## Privacy

This pipeline can touch Newsletter bodies, raw email, your personal filtering rules, and local knowledge-base paths. The default `.gitignore` already excludes:

- `config.yaml`, `sources.yaml` (your local config)
- `.env*`, `.venv/`, `cache/` (credentials and local artifacts)

Credentials are **only ever provided via environment variables or third-party OAuth**, never written into `config.yaml`. `paths.cache_dir` defaults to a location outside the repo (`~/.cache/ai-news-keji`), so raw email caches are never committed.

## Installation

### 1. Clone + install dependencies

```bash
git clone https://github.com/lovekeji-ai/ai-news-keji.git
cd ai-news-keji
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

### 2. Register with your agent

Claude Code:

```bash
mkdir -p ~/.claude/skills
ln -sfn "$(pwd)" ~/.claude/skills/ai-news-keji
```

Codex:

```bash
mkdir -p ~/.codex/skills
ln -sfn "$(pwd)" ~/.codex/skills/ai-news-keji
```

### 3. Invoke it

```text
/ai-news-keji
```

The agent takes over from there for both onboarding and daily use.

## Maintainer reference

A few internal scripts live in the repo. **End users don't need to call them directly** — the daily flow is entirely driven by the agent through `SKILL.md`. These are only useful for debugging or development:

- Health check: `.venv/bin/python scripts/doctor.py`
- Strict gate (run before fetch): `.venv/bin/python scripts/init.py --check`
- Compile check: `.venv/bin/python -m py_compile scripts/*.py`
- Pre-publish private-file check: `git status --short --ignored`

The full agent workflow (steps, caching, dedup, scoring) lives in [SKILL.md](SKILL.md).

## License

MIT. See [LICENSE](LICENSE).
