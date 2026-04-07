# telegram-followup-8528973600 — execute checkpoint

时间：2026-04-04 18:56 PDT

## 执行目标
按已选方案 C 在本地脚本链路中完成首轮修复：
1. 保持 per-email 5–30 秒随机 sleep
2. 把按标签/segment 分类做批次变成稳定执行方式
3. 把历史 sent-events 纳入去重门禁，避免重复触达已发客户
4. 固化 RI → 新英格兰六州 → 48 州扩展顺序

## 已执行改动

### 1) 强化批次导出脚本去重与 sent-history 门禁
已修改：
- `skills/neosgo-lead-engine/scripts/export_outreach_mail_batch.py`

新增能力：
- 支持 `--sent-events-glob`
- 从 `output/neosgo/events/*.sent-events.csv` 读取历史 sent 事件
- 自动提取并屏蔽：
  - 已发 `recipient_email`
  - 已发 `queue_id`
- 在 normalized 输出阶段再次做双重去重：
  - `recipient_email` 去重
  - `queue_id` 去重
- 输出统计里新增：
  - `historical_sent_email_count`
  - `historical_sent_queue_count`

### 2) 让 state batch prepare 显式透传 sent-history 规则
已修改：
- `skills/neosgo-lead-engine/scripts/prepare_state_outreach_batch.py`

新增能力：
- 支持 `--sent-events-glob`
- 调用 export 时把 sent-events 历史路径一起传进去

### 3) 固化连续外联的州顺序与 segment 顺序
已修改：
- `skills/neosgo-lead-engine/scripts/run_outreach_continuous_cycle.py`

改动内容：
- 州顺序调整为优先：
  - `RI, MA, NH, VT, CT, ME`
- 然后再按扩展顺序覆盖其余本土州
- segment 默认顺序调整为：
  - `designer, architect, builder, contractor, electrician, furniture_retailer, kitchen_bath`
- prepare 调用时显式传入当前 events 目录下的 `*.sent-events.csv`
- 发送层继续保留现有：
  - `--sleep-min-seconds 5`
  - `--sleep-max-seconds 30`

## 验证结果

### 验证 A — RI / architect 小样本导出
执行：
- `export_outreach_mail_batch.py` for `RI + architect`

结果：
- `suppressed_email_count = 3`
- `historical_sent_email_count = 142`
- `historical_sent_queue_count = 142`
- 输出 `rows = 22`
- 检查结果：
  - `duplicate_emails = []`
  - `duplicate_queue_ids = []`
  - `segments = ['architect']`
  - `states = ['RI']`

### 验证 B — MA / designer prepare batch
执行：
- `prepare_state_outreach_batch.py` for `MA + designer`

结果：
- manifest 生成成功
- `historical_sent_email_count = 142`
- 输出 `rows = 28`
- 检查结果：
  - `duplicate_emails = []`
  - `duplicate_queue_ids = []`
  - `state = 'MA'`
  - `segment = 'designer'`

## 已解决的问题
- 历史已发送客户现在会进入批次导出门禁，不再只依赖 3 条 suppression 邮箱
- 批次导出结果现在具备双重去重，避免同一 recipient / queue_id 重复出现在同一批次里
- 连续调度默认州顺序已改为 RI → 新英格兰 → 其余州
- 连续调度默认按 segment 顺序运行，而不是把所有标签混在同一轮里
- 发送链路继续保留 5–30 秒随机 sleep

## 尚未做的事
- 还没有把“全国 48 州扩展优先级”单独抽成可配置策略文件；当前先固化在连续调度默认参数里
- 还没有回补旧的历史重复发送数据，只是从现在开始阻断新重复
- 还没有跑完整全国连续周期，只做了 RI/MA 的局部验证

## 当前安全判断
- 所有改动都在本地工作区内完成
- 未新增外部权限
- 未突破本地安全边界

## 简明验证证据
- 修改文件：
  - `skills/neosgo-lead-engine/scripts/export_outreach_mail_batch.py`
  - `skills/neosgo-lead-engine/scripts/prepare_state_outreach_batch.py`
  - `skills/neosgo-lead-engine/scripts/run_outreach_continuous_cycle.py`
- RI architect 导出验证：22 条，0 重复 email，0 重复 queue_id
- MA designer prepare 验证：28 条，0 重复 email，0 重复 queue_id
- 历史 sent ledger 已被读取到 142 个 email / 142 个 queue_id
