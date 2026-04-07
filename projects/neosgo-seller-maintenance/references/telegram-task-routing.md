# Telegram Task Routing For NEOSGO Seller

为了避免以后任务越来越多时，Telegram 指令错误落到旧 followup 或不相关项目，建议把 `NEOSGO seller` 固定成一个 canonical task family。

## Canonical Task ID

- `neosgo-seller-maintenance`

## Allowed Sub-actions

- `import_new_giga_products`
- `optimize_existing_drafts`
- `resubmit_rejected_listings`
- `sync_uploaded_inventory`
- `report_status`

## Matching Strategy

1. 先匹配项目域
   - 关键词：`neosgo seller` / `giga` / `listing` / `draft` / `rejected` / `库存`

2. 命中项目域后，先绑定到 canonical task
   - 不再新建 `seller-neosgo-followup-*`
   - 统一先挂到 `neosgo-seller-maintenance`

3. 再识别子动作
   - `导入` -> `import_new_giga_products`
   - `draft` / `提审` -> `optimize_existing_drafts`
   - `rejected` / `重提` -> `resubmit_rejected_listings`
   - `库存` -> `sync_uploaded_inventory`
   - `进度` / `状态` -> `report_status`

4. 遇到混合指令
   - 仍然绑定 canonical task
   - 只更新 `requested_subactions` 列表
   - 禁止切根到 unrelated followup

## Safety Rules

- 若当前会话已绑定 `neosgo-seller-maintenance`，后续 seller 指令一律优先继续该 task
- 若输入同时包含 `marketing / lead / seo / geo`，必须切到其他项目，不允许混挂 seller task
- 若指令不含 seller 关键词，但会话已在 seller 任务里，优先做歧义检测，再决定是否切根

## Recommended Next Implementation

- 在 `brain_router` 前置增加一层 `project alias registry`
- 对 `NEOSGO seller` 使用固定 alias：
  - `neosgo seller`
  - `giga import`
  - `seller draft`
  - `seller rejected`
  - `seller inventory`
- alias 先命中项目，再进入自然语言意图判断
