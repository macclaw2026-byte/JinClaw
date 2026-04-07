# telegram-followup-8528973600 — understand checkpoint

时间：2026-04-04 18:35 PDT

## 目标理解
Jacken 这段语音的目标不是抽象建议，而是要把现有 Neosgo 外联/邮件连续发送链路改成可持续执行的具体规则：
1. 每封邮件之间的 sleep 改成 5–30 秒随机值
2. 按标签/细分（segment/tag）来做产品与发送批次
3. 已经发过的客户不再重复发送
4. 先从 RI 开始，然后覆盖新英格兰六州：RI、MA、NH、VT、CT、ME；之后再逐步扩展到美国本土 48 州，扩展顺序由系统决定

## 已完成的本地核查
- 读取现有连续执行 skill：`skills/continuous-execution-loop/SKILL.md`
- 核查当前邮件批次与事件产物：
  - `output/neosgo/mail-batch.json`
  - `output/neosgo/mail-batch-segmented.json`
  - `output/neosgo/mail-batch-preview.json`
  - `output/neosgo/events/RI-20260404T181938.sent-events.csv`
- 核查当前 bulk runner 与调度脚本：
  - `tools/bin/neosgo-seller-bulk-runner.py`
  - `tools/openmoss/ops/run_neosgo_seller_bulk_cycle.py`
- 核查当前 suppression 文件：`output/neosgo/suppressed-emails.json`

## 关键发现
### 1) 当前“已发不要重发”规则并没有真正闭环
- suppression 文件里目前只有 3 个邮箱：
  - `dprengaman@vision3architects.com`
  - `kdavignon@vision3architects.com`
  - `rdougald@autotempcontrols.com`
- 但 RI 实发事件文件显示，同一邮箱/同一 queue_id 已经被重复发送：
  - `eric.fiske@anchorinsulation.com` 发送了 2 次
  - `rowse@rowsearch.com` 发送了 3 次
  - queue_id `21df4cee0bb5fa4888993cd30e0ec0a2` 重复 2 次
  - queue_id `eaab1f134e2c832ad69cfe747c5c1639` 重复 3 次

结论：
- 当前系统虽然有 suppression 概念，但**没有把“已发送事件历史”强制并入去重门禁**
- 仅靠现有 suppression 文件不足以阻止重复发送

### 2) 分标签批次已经有雏形，但还不稳定
- `mail-batch-segmented.json/csv` 已经含有 `segment_primary`、`template_version` 等字段
- RI 实发事件也显示当前批次已经混合了：
  - `contractor`
  - `designer`
  - `architect`

结论：
- “按标签分类做产品/发送”已有字段基础
- 但目前更像“同州混合批次”，还不是严格的 segment-first 或 tag-first 执行策略

### 3) Sleep 目前不是 5–30 秒随机值
- 已定位到现有脚本中固定 sleep 逻辑的证据：
  - `tools/bin/neosgo-seller-bulk-runner.py` 仅支持固定 `--sleep-seconds`
- RI 实发事件时间间隔也表现为近似固定 2–3 秒节奏，不符合 5–30 秒随机要求

结论：
- 需要在实际发送链路中引入 `random.uniform(5, 30)` 级别的 per-email sleep，而不是固定值

### 4) RI 已经在实际发送，但州扩展策略尚未形成可持续治理规则
- `output/neosgo/events/RI-20260404T181938.sent-events.csv` 证明 RI 已经开始发
- 但当前没有证据表明“新英格兰六州优先、之后再扩展到 48 州”的顺序已经被编码为调度策略

## 已验证 blocker 定义
当前 blocker 不是“系统完全不能发”。
当前 blocker 是：
1. 去重门禁只覆盖少量 suppression 邮箱，**未覆盖实际 sent-events 历史**
2. 当前批次仍可能把同一 recipient / queue_id 重复写入并发送
3. Sleep 规则仍是固定/短间隔，而不是 5–30 秒随机
4. 州扩展顺序还未被固化成 durable policy
5. segment/tag 分类虽已有字段，但尚未成为强约束的发信组织逻辑

## 执行阶段应做的具体修复方向
1. 在外联批次生成/发信前增加双重去重：
   - `recipient_email` 去重
   - `queue_id` 去重
2. 把历史 sent-events 汇总进 suppression / sent-ledger，确保已发客户不会再次进入待发批次
3. 将 per-email sleep 改为 `random`，范围 5–30 秒
4. 把州级 rollout policy 固化为：
   - Wave 1: RI
   - Wave 2: MA, NH, VT, CT, ME
   - Wave 3+: 其余 42 个本土州，按系统定义优先级扩展
5. 将 segment/tag-first 作为批次切分规则，而不是混合批量直接发送

## 当前安全判断
- 需求可在本地工作区内修复，不需要突破新的安全边界
- 不需要新增高风险外部权限
- 下一步应继续在本地代码/状态层完成修复与验证

## 简明验证证据
- `output/neosgo/mail-batch-segmented.json` 已含 `segment_primary`
- `output/neosgo/suppressed-emails.json` 当前仅 3 个邮箱
- `output/neosgo/events/RI-20260404T181938.sent-events.csv` 中：
  - `eric.fiske@anchorinsulation.com` 出现 2 次
  - `rowse@rowsearch.com` 出现 3 次
- `tools/bin/neosgo-seller-bulk-runner.py` 当前只显示固定 `--sleep-seconds` 机制
