# telegram-followup-8528973600 — plan checkpoint

时间：2026-04-04 18:39 PDT

## 目标
为 Neosgo 连续外联链路选择最安全、最小改动、但能真正满足 Jacken 新要求的执行路径：
- 每封之间 5–30 秒随机 sleep
- 按标签/segment 分类做产品与发送
- 已发客户不再重复发送
- 先 RI，再新英格兰六州（RI/MA/NH/VT/CT/ME），再扩展到美国本土 48 州

## 已对比的候选方案

### 方案 A — 只调整发送脚本 sleep 参数
**做法**
- 仅依赖 `send_outreach_mail_batch.py` 现有 `--sleep-min-seconds/--sleep-max-seconds`
- 不改批次生成与去重规则

**优点**
- 改动最小
- 可立即让 sleep 变成随机 5–30 秒

**缺点**
- 不能解决重复发送
- 不能把 segment/tag-first 变成强约束
- 不能把 RI→新英格兰→48 州固化为 durable rollout policy

**结论**
- 不足以满足 done definition

---

### 方案 B — 只改连续调度脚本 `run_outreach_continuous_cycle.py`
**做法**
- 在循环层限制 states 顺序
- 在循环层按 segment 遍历
- 继续复用现有 prepare/send/report 脚本

**优点**
- 可以较快把州顺序和 segment 遍历顺序固化下来
- 已看到当前脚本默认支持 `states` 和 `segments` 参数
- 当前脚本已经把发送调用成 `--sleep-min-seconds 5 --sleep-max-seconds 30`

**缺点**
- 批次文件本身仍可能包含重复 recipient / queue_id
- sent-events 历史没有自动并入 suppression/ledger
- 如果 prepare/export 源头不去重，调度层只能部分缓解，无法闭环

**结论**
- 比方案 A 强，但仍不足以根治“已发不重发”

---

### 方案 C — 源头去重 + 调度策略固化 + 发送层保留随机 sleep（推荐）
**做法**
1. 在批次导出/准备阶段加入强制去重：
   - `recipient_email` 去重
   - `queue_id` 去重
   - 合并历史 `sent-events` 为 sent-ledger / suppression 输入
2. 在连续调度脚本中固化 rollout policy：
   - Wave 1: RI
   - Wave 2: MA, NH, VT, CT, ME
   - Wave 3+: 其余本土州，按系统定义顺序扩展
3. 在连续调度脚本中把 segment/tag-first 作为主循环，而不是混合批次
4. 发送层继续使用已存在的 `--sleep-min-seconds 5 --sleep-max-seconds 30`

**优点**
- 同时覆盖 4 个核心要求
- 最大化复用现有脚本：
  - `prepare_state_outreach_batch.py`
  - `export_outreach_mail_batch.py`
  - `send_outreach_mail_batch.py`
  - `run_outreach_continuous_cycle.py`
- 只需在本地代码与本地状态层修复，不需要新增外部权限
- 与 `customer-development-sop.md` 的“触达前检查 / recently contacted / do_not_contact / 事件回写”一致

**缺点**
- 改动比 A/B 多
- 需要额外验证历史 sent-events 汇总逻辑，避免误伤未发潜客

**结论**
- 最符合业务目标与安全边界
- 应作为 execute 阶段的选定方案

---

### 方案 D — 全部推倒重做成新系统
**做法**
- 新写一套外联队列、发送器、州策略、事件台账

**优点**
- 设计自由度高

**缺点**
- 风险与变更面过大
- 会绕开已有产物与运行痕迹
- 不符合 local-first / minimal-safe-change 原则

**结论**
- 不选

## 最终选定方案
**选定：方案 C — 源头去重 + 调度策略固化 + 发送层保留随机 sleep**

## 选择理由
1. 当前 `send_outreach_mail_batch.py` 已经支持随机 sleep 参数，所以 sleep 要求无需大改，只要确认执行链路一直传入 5–30 秒
2. 真正缺的是“批次源头去重”和“sent-events 历史并入门禁”
3. `run_outreach_continuous_cycle.py` 已具备按 state/segment 双层循环的骨架，适合固化 RI→新英格兰→全国 rollout
4. 该方案完全在本地工作区和现有脚本体系内完成，安全边界最稳

## execute 阶段建议落点
1. 先读并修改：`skills/neosgo-lead-engine/scripts/export_outreach_mail_batch.py`
2. 其次修改：`skills/neosgo-lead-engine/scripts/prepare_state_outreach_batch.py`
3. 再修改：`skills/neosgo-lead-engine/scripts/run_outreach_continuous_cycle.py`
4. 必要时新增一个本地 sent-ledger 汇总脚本或 JSON 状态文件
5. 最后用 RI / MA 小样本验证：
   - 无重复 recipient
   - 无重复 queue_id
   - state 顺序正确
   - segment 切分正确
   - send 层 sleep 参数仍为 5–30 秒随机

## 当前安全判断
- 不需要突破本地安全边界
- 不需要新的敏感权限
- 仅涉及本地代码、批次文件、事件文件、状态文件修复

## 简明验证证据
- `run_outreach_continuous_cycle.py` 当前已调用：`--sleep-min-seconds 5 --sleep-max-seconds 30`
- `send_outreach_mail_batch.py` 当前确实支持随机 sleep 区间
- `customer-development-sop.md` 已明确要求触达前检查“是否最近已触达”
- `mail-integration.md` 明确当前流程核心仍是 export → send/draft → import events，适合在此链路补强去重与 rollout policy
