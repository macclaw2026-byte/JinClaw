<!--
RULES-FIRST NOTICE:
Before modifying this file, first read:
- `JINCLAW_CONSTITUTION.md`
- `AI_OPTIMIZATION_FRAMEWORK.md`
Follow the constitution and framework:
brain-first, one-doctor, fail-closed, evidence-over-narration,
validate locally, then use the required PR workflow.
-->
# NEOSGO Seller Maintenance

这条工作流是 `NEOSGO seller + GIGA` 的唯一主流程，替代之前散落在 `seller-neosgo*` 各种 followup 里的历史任务。

## Canonical Workflow

每天运行一次，固定完成 4 个阶段：

1. `Import New`
   - 扫描 GIGA candidates
   - 只导入 `NEW_IMPORT + canImport=true`
   - 如果 draft 里已有相同 SKU，直接跳过

2. `Optimize Draft`
   - 对当前 `DRAFT` listing 统一补齐稳定字段
   - 描述强制转成纯文本
   - 修正 `packingUnits / quantityAvailable / shipping template / warehouse`
   - readiness 通过后直接提交审核

3. `Repair Rejected`
   - 枚举当前 `REJECTED`
   - 重新跑优化 payload
   - readiness 通过后再次提交审核

4. `Sync Uploaded Inventory`
   - 每日同步已上传 listing 的库存
   - 当前覆盖 `APPROVED / SUBMITTED`
   - 库存来源以 GIGA candidate 的 `quantityAvailable` 为准

## Commands

手动运行一轮：

```bash
python3 /Users/mac_claw/.openclaw/workspace/tools/openmoss/ops/run_neosgo_seller_maintenance_cycle.py
```

安装每日调度：

```bash
/bin/zsh /Users/mac_claw/.openclaw/workspace/tools/openmoss/ops/install_neosgo_seller_maintenance_launch_agent.sh
```

## Outputs

- JSON 报告：
  `/Users/mac_claw/.openclaw/workspace/output/neosgo-seller-maintenance/`
- 最新 state：
  `/Users/mac_claw/.openclaw/workspace/data/neosgo-seller-maintenance-state.json`

## Legacy Task Retirement Tracking

截至 2026-04-12，legacy `seller-neosgo*` 任务链的 retirement 审计文件位于：

- `projects/neosgo-seller-maintenance/references/legacy-seller-neosgo-retirement-audit-2026-04-12.md`

这份清单用于明确哪些历史 task-status 记录仍残留在 active task space，直到它们被正式归档/退休为止。

## Why This Replaces The Old Task Chain

旧链条的问题是：

- `seller-neosgo*` followup 太多，目标漂移
- 有的任务是图片/浏览器动作，有的是 API 规则，有的是营销项目串进来
- runtime 里大多数都被 `await_project_crawler_remediation` 卡死

新的 daily workflow 只保留稳定、可 API 化、可重复执行的核心：

- 新品导入
- draft 优化并提审
- rejected 重提
- 每日库存同步

图片生成与更复杂的富媒体维护，不再作为 daily blocker；后续如需恢复，应单独挂成辅助 lane。
