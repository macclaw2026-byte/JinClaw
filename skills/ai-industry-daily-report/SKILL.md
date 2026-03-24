---
name: ai-industry-daily-report
description: Generate a concise but high-signal daily AI industry report for Jacken. Use when asked for daily or scheduled AI reports, including AI industry news, concept explanations, model/company/tool updates, and forward-looking trend analysis. Also use when preparing a test edition before enabling an automated schedule.
---

# AI Industry Daily Report

Generate a daily AI report in Chinese for Jacken.

## Output goals

Each report should be useful in under 5 minutes of reading while still feeling substantive.

Required sections:

1. **今日AI行业新闻**
2. **AI概念卡片** — explain 2-4 concepts in plain Chinese
3. **未来趋势判断** — short forward-looking analysis
4. **值得关注** — what to watch in the next 24-72 hours

## Source strategy

Prefer public, high-signal sources. Use a mix of:

- official company blogs / newsrooms
- major model-provider announcement pages
- reputable tech reporting
- direct product / research release pages when available

If search is weak, use known strong public sources directly and clearly state confidence.

## Recommended source families

- OpenAI newsroom / blog
- Anthropic news / engineering blog
- Google / DeepMind blog
- Meta AI blog
- Microsoft / Azure AI blog
- NVIDIA blog
- Hugging Face blog
- TechCrunch AI
- The Verge AI

## Report style

- Write in Chinese
- Be information-dense, not fluffy
- Avoid sensationalism
- Separate confirmed facts from inference
- If a source is weak or unavailable, say so briefly rather than pretending certainty

## Structure template

Use this structure:

**AI行业日报 | YYYY-MM-DD**

**一、今日AI行业新闻**
- 3-6 items
- each item should include: what happened / why it matters / possible impact

**二、AI概念卡片**
- choose 2-4 concepts relevant to current industry movement
- for each concept include:
  - 是什么
  - 为什么重要
  - 一个简单例子

**三、未来趋势判断**
- 3-5 bullets
- focus on productization, model competition, infra, agents, regulation, enterprise adoption, robotics, open source, or multimodal evolution

**四、接下来值得关注**
- 2-4 bullets for near-term watchlist

**五、一句话总结**
- 1 short closing synthesis

## Scheduling behavior

When this is run on a schedule for Jacken:

- deliver the report directly to Telegram chat 8528973600
- keep the body readable in chat
- if there is a file attachment or markdown artifact, the chat message should still stand on its own

## Quality bar

Before finalizing, check:

- at least 3 concrete news items
- at least 3 concept explanations
- at least 2 new-term / new-research items when evidence permits
- at least 3 trend bullets
- no obvious duplicate items
- language is natural Chinese
- explanations are understandable to a smart non-specialist
ews items
- at least 2 concept explanations
- at least 3 trend bullets
- no obvious duplicate items
- language is natural Chinese
a file attachment or markdown artifact, the chat message should still stand on its own

## Quality bar

Before finalizing, check:

- at least 3 concrete news items
- at least 2 concept explanations
- at least 3 trend bullets
- no obvious duplicate items
- language is natural Chinese
