---
name: temu-data-statistics
description: Execute TEMU monthly data statistics workflows. Use when asked to build TEMU monthly order profit sheets, full-store finance summaries, shipping label fee matching, delay-rate reports, false/fraud shipment penalty checks, pickup/chargeback cost summaries, or after-sales analysis from TEMU Seller Central, ERP, OMS, and finance/account-center exports. Pair with ziniao-assistant when browser-backed seller-console export operations are required.
---

# TEMU Data Statistics

Use this skill when the task is to produce or verify TEMU monthly statistics from seller-console and internal ERP/OMS exports.

Before executing, read [references/monthly-statistics-workflow.md](references/monthly-statistics-workflow.md). It contains the extracted SOP from the source Word document, including required exports, formulas, matching keys, and output contracts.

## Operating Rules

- Preserve every raw export unchanged. Work only on copied/normalized sheets.
- Treat missing source files, missing required columns, ambiguous store/month, or unmatched key rates above tolerance as blockers.
- Use evidence over narration: record source export filenames, export date ranges, row counts before/after filtering, formulas applied, unmatched counts, and final output paths.
- If seller-console interaction is needed, use `ziniao-assistant` and its validated browser rules. Do not invent browser tools or bypass authenticated-session governance.
- Do not commit raw exports, screenshots, order IDs, account data, or customer/shipping details.

## Monthly Cadence

- 月度订单统计：每月 10 号之前完成。
- 店铺总数据汇总：每月 10 号左右完成。
- 延迟率统计：每月 20 日之前完成。
- 售后情况统计：每月 20 日之前完成。

## Execution Shape

1. Identify target month, country/site, store, subject/company, and whether the task is order-profit, store-summary, delay-rate, after-sales, or all.
2. Collect required exports from TEMU Seller Central plus ERP/OMS sources listed in the workflow reference.
3. Normalize headers and dates; preserve raw sheets.
4. Apply the workflow formulas and matching rules.
5. Produce the requested workbook or structured summary.
6. Verify row counts, unmatched records, formula coverage, and totals.
7. Return a concise completion report with artifacts, evidence, blockers, and unresolved assumptions.

## Output Contract

Every completed run should report:

- `target_month`
- `stores`
- `source_exports`
- `raw_row_counts`
- `filtered_row_counts`
- `unmatched_counts`
- `formula_checks`
- `output_files`
- `known_risks`

If any required data is missing, stop with a blocker report instead of filling unknown values silently.
