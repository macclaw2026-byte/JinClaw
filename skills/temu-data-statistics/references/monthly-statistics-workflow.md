# TEMU Monthly Statistics Workflow

This reference is distilled from `/Users/mac_claw/Downloads/TEMU数据统计步骤.docx`. The original document contains screenshots with real order/store data, so this skill stores the workflow as text instead of bundling the raw images.

## Scope

The workflow covers four recurring monthly jobs:

- 月度订单统计
- 店铺总数据汇总
- 延迟率统计
- 售后情况统计

Use the workflow for TEMU US seller-console data unless the user explicitly gives another site/country. When browser operation is required, use the `ziniao-assistant` skill to operate the authenticated seller console.

## Source Systems

Required or common sources:

- TEMU Seller Central: `订单管理 -> 订单列表`
- TEMU Seller Central: `商品管理 -> 上新生命周期管理`
- TEMU Seller Central: `账户资金 -> 对账中心/结算数据/发货面单费`
- ERP: `采购单`
- ERP: `销售出库单`
- ERP: `产品管理` dimensions/weight
- OMS: 一件代发出库
- Monthly exchange rate sheet
- Monthly logistics unit-price sheet

## Raw Export Discipline

- Save every original export in a raw folder with source, store, month, and export timestamp.
- Never delete rows from the raw sheet. Filter/copy into a working sheet.
- Record row counts at each stage: raw rows, rows with tracking number, rows after warehouse filter, rows after one-order-multiple-piece filter, delayed rows, unmatched rows.
- If a required column is absent, stop and report `missing_required_column`.

## Job 1: 月度订单统计

### Goal

Produce a monthly order-level profit sheet.

### TEMU order export

Seller console path:

`Seller Central -> 订单管理 -> 订单列表`

Actions:

1. Select country/site as `美国` when applicable.
2. Select target month in `订单创建时间`.
3. Click `导出订单`.
4. In export fields, include at least:
   - `订单号`
   - `订单状态`
   - `应履约件数`
   - `商品名称`
   - `SKU ID`
   - `SKC ID`
   - `SPU ID` when available
   - `SKU货号`
   - `商品属性`
   - `运单号`
   - `包裹号`
   - `物流商`
   - `发货仓`
   - `订单创建时间`
   - `要求最晚发货时间`
   - `实际发货时间`
   - `预计送达时间`
   - `实际签收时间`
5. Export and store the raw file.

### Filter cancelled/no-tracking orders

In the working copy:

1. Filter `运单号`.
2. Remove or exclude blank/`--`/missing tracking-number rows.
3. Treat these rows as cancelled/no-shipment rows and do not count them in order profit statistics.

### Product lifecycle declaration price

Seller console path:

`商品管理 -> 上新生命周期管理`

Actions:

1. Copy the order `SKU货号` values from the working order sheet.
2. Search these SKU codes in `上新生命周期管理`.
3. Export product lifecycle data.
4. Match declaration price back to the order sheet by `SKU货号` or the strongest available SKU key.

Required matched field:

- `申报价`

### Selling price formula

Base formula from the source SOP:

```text
售价 = [(申报价 * 履约件数 / 汇率) + 2.99] * 0.8
```

Exception:

- If the base USD amount is greater than 30 USD, do not add the `2.99` subsidy.

Recommended spreadsheet formula shape:

```text
base_usd = 申报价 * 履约件数 / 汇率
售价 = IF(base_usd > 30, base_usd * 0.8, (base_usd + 2.99) * 0.8)
```

### Purchase cost / purchase price

Rules:

- `Y2`: match purchase cost from ERP `采购单`.
- `Y1`: match purchase cost from ERP `销售出库单`.
- `进价 = 进价人民币 * 履约件数 / 汇率`.

Common matching keys:

- `订单号`
- `销售出库单号`
- `SKU货号`
- `SKU ID/SKC ID`
- `运单号`

If multiple rows match one order, aggregate only according to the order quantity and flag the row as `multi_match_review_required`.

### First-leg shipping cost

Rules:

- `Y2`: derive from ERP `产品管理` dimensions/weight multiplied by the monthly logistics unit price.
- `Y1`: derive from ERP `销售出库单` export.

Required inputs:

- Product weight/dimensions
- Fulfillment quantity
- Monthly logistics unit price
- Warehouse/route when relevant

### Operation fee

Formula:

```text
操作费 = 0.4 USD per order
```

Important:

- For one order with multiple pieces, do not blindly multiply by pieces. The SOP states one order is `0.4 USD`; handle multi-piece orders deliberately and document the allocation rule.

### Tail-end shipping label fee

Seller console path:

`账户资金 -> 发货面单费`

Timing:

- Export around the 20th to 22nd of the following month.

Filter:

- `账单支出/退款时间` should cover the target month or the settlement window requested by the user.

Formula:

```text
发货面单费 = 支出 + 调整支出 - 退款调整
```

Spreadsheet safeguards:

```text
ABS(value) for negative source amounts when needed
IFERROR(支出 + 调整支出 - 退款调整, 0)
```

Match by:

- `运单号`
- `包裹号`
- `订单号` as fallback when tracking-level matching is unavailable

### Profit formula

Order-level formula:

```text
利润 = 售价 - 进价 - 头程 - 操作费 - 尾端配送费
```

If the local template has separate `采购成本` and `进价` columns, use the template's existing semantics and avoid double-counting. Report the chosen formula in `formula_checks`.

### Monthly order output columns

Recommended order:

- `订单号`
- `订单状态`
- `应履约件数`
- `商品名称`
- `SKU ID`
- `SKC ID`
- `SKU货号`
- `商品属性`
- `运单号`
- `物流商`
- `发货仓`
- `订单创建时间`
- `申报价`
- `售价`
- `进价`
- `头程`
- `操作费`
- `尾端配送费`
- `进价（人民币）`
- `利润`
- `利润率`
- `汇率`
- `开发/负责人`

## Job 2: 店铺总数据汇总

### Goal

Build or update the monthly full-store sales/finance summary.

### Summary dimensions

Use at least:

- `月份`
- `主体`
- `店铺`

### Summary metrics

The source SOP tracks:

- `已到账款项`
- `待处理款项`
- `采购成本`
- `头程`
- `操作费`
- `发货面单费`
- `退货面单费`
- `延迟到货`
- `虚假发货`
- `欺诈发货`
- `上门取件`
- `买家拒付`
- `其它`
- `毛利润`
- `毛利率`

### 已到账款项 / 待处理款项

Seller console source:

`账户资金` summary pages.

Actions:

1. Select country/site and target store.
2. Select target month or account period.
3. Capture values for received and pending funds.
4. Record whether the value is by order time, settlement time, or bill time.

### 采购成本 / 头程 / 操作费

Use the monthly order statistics workbook as the preferred source when it has already been completed.

Aggregation:

- `采购成本`: sum order-level purchase cost.
- `头程`: sum order-level first-leg cost.
- `操作费`: sum order-level operation fee.

### 发货面单费

Use the same rule as Job 1:

```text
发货面单费 = 支出 + 调整支出 - 退款调整
```

Notes:

- Convert source values to absolute values when the source system exports expenses as negative amounts.
- If order statistics already adjusted the value, reuse that checked value.
- Otherwise re-export and match.
- Use `IFERROR(..., 0)` for unmatched/NA rows so totals can calculate, but still report unmatched counts.

### 退货面单费

Formula:

```text
退货面单费 = 支出 + 调整支出 - 退款调整
```

Match by order/tracking where possible. Use bill time when the metric asks for bill-time expense.

### 延迟到货

Penalty formula:

```text
延迟到货 = 延迟单量 * 40
```

Delay definition:

```text
实际签收时间 - 预计送达时间 > 0
```

Exclude rows without tracking number.

### 虚假发货

Workflow:

1. Export all orders for the target month from `订单列表`.
2. Pull finance/account-center data for the required months.
3. Combine account-center data into one finance table.
4. Match finance amounts back to the order list.
5. Keep month-over-month cumulative finance data, because the account center only exposes financial rows and later months may need prior-month matching context.

### 上门取件 / 买家拒付 / 其它

Use the order list or finance/account-center category export as the source. The screenshot marks several columns in yellow as fields to match against the backend order list. Preserve the category source and matching key in evidence.

### 毛利润 / 毛利率

Recommended formulas:

```text
毛利润 = 已到账款项 - 采购成本 - 头程 - 操作费 - 发货面单费 - 退货面单费 - 延迟到货 - 虚假发货 - 欺诈发货 - 上门取件 - 买家拒付 - 其它
毛利率 = 毛利润 / 已到账款项
```

If the user's existing workbook has a different formula contract, preserve the workbook contract and report it.

## Job 3: 延迟率统计

### Goal

Analyze delayed orders by store and summarize delay causes.

### Output A: 单店铺延迟小计

The single-store summary should include:

- Store name
- Order creation period
- Unreceived subtotal
- Received subtotal
- Delay order total
- Total order count
- Delay order rate
- Notes

Recommended buckets:

- 未签收情况下后台状态：`后台已取消`, `后台已发货`
- 未签收情况下 OMS 状态：`仓库处理中`, `OMS已取消`, `OMS已出库`
- 已签收尾端运输时间：`7天内（含7天）`, `8-10天`, `11-15天`, `16天及以上`
- 已签收头程运输时间：`10天内`, `10-12天`, `13-15天`, `16天及以上`

### Output B: 总店铺延迟汇总

Columns:

- `小组`
- `店铺`
- `月份`
- `延迟单量`
- `总单量`
- `延迟率`
- `月组平均延迟率` when required

Formula:

```text
延迟率 = 延迟单量 / 总单量
```

### Detailed delay workflow

#### Step 1: Export previous month's all orders

Seller console path:

`订单管理 -> 订单列表`

Actions:

1. Select previous month in `订单创建时间`.
2. Export all orders.
3. Include `订单信息`, `运单信息`, and `操作节点/时间节点` fields.

#### Step 2: Filter but preserve raw export

On a working copy:

1. Filter `运单号`; exclude blank/`--` rows.
2. Filter `发货仓`; exclude overseas-warehouse rows.
3. Exclude one-order-multiple-piece rows for the Y2 total-order denominator when required by the workbook.
4. Do not mutate the raw export.

Important source note:

- The SOP says `取消单不可过滤`. Interpret this as: do not filter out cancelled orders merely by order status before the required tracking/warehouse/order-piece denominator logic is applied. If a cancelled row has no tracking number, it will still be excluded by the tracking rule.

Denominator:

```text
当月Y2总单量 = rows after excluding no-tracking + overseas warehouse + one-order-multiple-piece rows
```

#### Step 3: Calculate delay days

Formula:

```text
延迟天数 = 实际签收时间 - 预计送达时间
```

Delay order:

```text
延迟天数 > 0
```

#### Step 4: Filter delayed orders

Use custom filter on the delay-days column:

```text
延迟天数 > 0
```

#### Step 5: Match OMS outbound data

Actions:

1. Copy delayed order numbers.
2. Go to OMS `一件代发出库`.
3. Search/export matching outbound records.
4. Match OMS data back to delayed orders.

Expected OMS fields:

- `出库时间`
- `OMS状态`
- `销售出库单号`
- `平台单号/订单号`
- `物流商`
- `仓库`

#### Step 6: Normalize date formats

For date/time columns, use a consistent date-time format such as:

```text
yyyy-m-d h:mm
```

For duration columns, use a readable duration format such as:

```text
[h]"小时"
```

or the workbook's existing day/hour display format.

#### Step 7: Add duration columns

Add four analysis columns when source data is available:

- `头程时间（出库时间 - 订单创建时间）`
- `尾端送达时间（实际签收时间 - 出库时间）`
- `出库到上网时间（上网时间 - 出库时间）`
- `尾端超时时间（实际签收时间 - 上网时间）`

If `上网时间` is unavailable, keep the related columns blank and report `missing_network_scan_time`.

#### Step 8: Format and summarize

Create the single-store subtotal and update the total-store delay summary.

Verification:

- `延迟单量` equals rows where `延迟天数 > 0`.
- `总单量` equals the agreed denominator after exclusions.
- Store/month totals reconcile to the total-store summary.

## Job 4: 售后情况统计

### Goal

Analyze after-sales situation by subject, store, and operator to identify causes and reduce after-sales rate.

### Source windows

The screenshot notes:

- `已到账款项` should be grouped by bill/account data.
- `订单创建时间` can be selected by target month, for example `2月1号-28号`.

### Recommended columns

- `序号`
- `负责人`
- `账号名称`
- `店铺名称`
- `店铺类型`
- `退货面单费（按账单时间）`
- `销售金额总和`
- `退货面单费占比`
- `销售冲回`
- `销售回款`
- `售后率（冲回/回款）`
- `售后原因`

### Metrics

Recommended formulas:

```text
退货面单费占比 = 退货面单费 / 销售金额总和
售后率 = 销售冲回 / 销售回款
```

Use subtotals by负责人/account/store group and a final total row.

### 售后原因 field

The `售后原因` column should be qualitative, not just numeric. Extract or write reasons based on:

- High-return products/SKUs
- Product not suitable for target household/use case
- Inventory clearance effects
- Product quality complaints
- Wrong expectations from listing/content
- Shipping damage
- Refused delivery or no delivery
- Seasonal or promotional abnormality
- Existing notes from operators

If a reason is inferred rather than directly supported, label it as `inferred`.

## Browser Export Checklist

When using `ziniao-assistant` or another approved browser bridge:

1. Resolve and open the correct store once.
2. Confirm login/session is already authenticated.
3. Confirm country/site is `美国` unless the user specifies otherwise.
4. Navigate to the target page.
5. Set target date range.
6. Export with the required fields.
7. Confirm the file exists and has nonzero size.
8. Record page, date range, export type, and filename.

Do not continue if the browser bridge is unreachable or if an export cannot be confirmed.

## Verification Checklist

For every workbook:

- Raw exports are preserved.
- Required columns are present.
- Dates were parsed successfully.
- Row counts are recorded before/after filtering.
- Formula columns have no unexpected blanks.
- `IFERROR(...,0)` rows are counted and reviewed.
- Matching keys have acceptable unmatched counts.
- Totals reconcile between detail sheets and summary sheets.
- Any inferred or manually adjusted values are listed in `known_risks`.

## Blocker Report Template

Use this shape when the workflow cannot safely complete:

```json
{
  "status": "blocked",
  "target_month": "",
  "store": "",
  "blocked_reason": "",
  "missing_sources": [],
  "missing_columns": [],
  "ambiguous_rules": [],
  "safe_next_actions": []
}
```
