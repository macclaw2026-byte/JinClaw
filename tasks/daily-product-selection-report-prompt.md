# Daily Product Selection Report Prompt

Use `product-selection-engine` as the primary skill.
Use `continuous-execution-loop` if the run needs multiple internal stages.
Use `resilient-external-research` for external data gathering.
Use `guarded-agent-browser-ops` only when browser-driven public page analysis is needed.
Use `error-recovery-loop` if a recoverable tool or source error appears.

Goal:
Produce a detailed daily product-selection report focused on US ecommerce opportunities.

Required workflow:
1. Read and follow these local files when relevant:
   - `/Users/mac_claw/.openclaw/workspace/skills/product-selection-engine/SKILL.md`
   - `/Users/mac_claw/.openclaw/workspace/skills/product-selection-engine/references/data-sources-and-signals.md`
   - `/Users/mac_claw/.openclaw/workspace/skills/product-selection-engine/references/decision-framework.md`
2. Gather fresh public methodology/trend/platform signals relevant to ecommerce product selection.
3. Use multiple public sources. Do not depend on one website. If a source is blocked, incomplete, or low-confidence, switch sources and continue.
4. Prioritize trends and candidate products/categories that look commercially relevant.
5. Analyze public demand, trend quality, platform behavior signals, competition density, and business viability.
6. If exact sales data is unavailable, use careful proxy signals and say so explicitly.
7. Create a structured Excel report in `/Users/mac_claw/.openclaw/workspace/reports/product-selection/` with a timestamped filename like `daily-product-selection-report-YYYYMMDD.xlsx`.
8. Include multiple sheets where useful, such as:
   - Executive Summary
   - Trend Signals
   - Candidate Products
   - Competition Snapshot
   - Product Scorecard
   - Recommendations
9. Keep the report useful even if some sources are partially unavailable. Prefer partial-but-solid output over failing entirely.
10. After generating the Excel file, send it to Jacken on Telegram chat `8528973600` using the message tool as an attachment.
11. Also include a short plain-language summary highlighting the most promising opportunities and biggest watch-outs.
12. Trigger `safe-learning-log` judgment after completion and note if the product-selection framework should improve.

Report quality requirements:
- Do not fabricate certainty.
- Mark confidence where signals are weak.
- Use public/authorized information only.
- Prefer evidence-backed reasoning over hype.
- If a fetch/browser/source fails but the task can still be completed with alternate public sources, continue and note the limitation.
