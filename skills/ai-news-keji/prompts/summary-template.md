---
created: {{DATE}}
updated: {{TODAY}}
type: 每日摘要
raw: "[[{{DATE}}]]"
stats:
  原始条目: {{RAW_COUNT}}
  去重去噪后: {{DEDUP_COUNT}}
  行业大事: {{INDUSTRY_COUNT}}
  对我有用: {{PERSONAL_COUNT}}
  值得关注: {{WATCH_COUNT}}
---

# 每日新闻摘要 {{DATE}}

---

## 🌍 今日行业大事

### {{TITLE}}

覆盖源：{{SOURCE_COUNT}}
类别：{{CATEGORY}}
形态：{{FORMAT}}

{{FACT_PARAGRAPH}}

{{IMPACT_PARAGRAPH}}

主源：[{{SOURCE_NAME}}]({{SOURCE_URL}})
其他来源：{{OTHER_SOURCES}}

---

<!-- 每条之间用 --- 分隔。预期 2-4 条，可以为 0。不凑数。 -->

## 🎯 今日对我有用

### {{TITLE}}

评分：{{SCORE}}
类别：{{CATEGORY}}
形态：{{FORMAT}}

{{CONTENT_PARAGRAPH}}

{{WHY_USEFUL_PARAGRAPH}}

主源：[{{SOURCE_NAME}}]({{SOURCE_URL}})
其他来源：{{OTHER_SOURCES}}

---

<!-- 每条之间用 --- 分隔。预期 3-5 条，可以为 0。不凑数。 -->

## 值得关注

- **{{TITLE}}** {{CATEGORY}} · {{FORMAT}} — {{ONE_LINE_SUMMARY}}。[链接]({{URL}})

---

## 今日关键信号

1. **{{TREND_NAME}}** — {{TREND_ANALYSIS}}
