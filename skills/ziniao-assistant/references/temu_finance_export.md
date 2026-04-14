# Temu Finance Export Workflow

Validated Ziniao-assisted workflow for Temu seller finance export.

## Target

- Platform host: `seller.kuajingmaihuo.com`
- Landing page: `https://seller.kuajingmaihuo.com/labor/bill`
- Business path:
  `账户资金 -> 对账中心 -> 财务明细`

## Proven working sequence

1. Open the bound store in Ziniao and reuse the saved authenticated profile.
2. Navigate to `https://seller.kuajingmaihuo.com/labor/bill`.
3. If authorization/region selection appears:
   - choose `美国`
   - click the visible consent checkbox/label
   - trigger the visible `确认授权并前往` action
4. Confirm the page is `对账中心`.
5. Enter the `财务明细` tab.
6. Open the date filter and set the range to:
   - start: `2026-03-01 00:00:00`
   - end: `2026-03-31 23:59:59`
7. Click `查询`.
8. Verify the table reflects March data.
9. Click `导出`.
10. In the export modal, keep the default `导出列表` if no other export shape is requested.
11. Click `确认`.
12. Open `导出历史`.
13. Verify a new top row exists with:
   - the expected March date range
   - export content `列表数据`
   - a generated time consistent with the current run
14. Wait until the row reaches the downloadable state such as `下载数据报表`.

## Important implementation notes

- The date picker is component-controlled. Directly writing raw DOM values may fail silently.
- Use visible picker interactions or a component-friendly script path that triggers the component’s own events.
- The final success criterion is not “clicked export”; it is “new export-history row created with the requested date range and downloadable status”.

## Completion proof example

Strong proof includes:

- a screenshot of the March-filtered result page
- a screenshot of export history showing the new row
- row metadata containing:
  - query time `2026-03-01 00:00:00 ~ 2026-03-31 23:59:59`
  - export content `列表数据`
  - downloadable action `下载数据报表`
