# data-followup-3 — plan checkpoint

时间：2026-04-05 19:29 PDT

## 计划阶段目标
比较多个安全执行路径，并选出当前最合适的已批准路线；不做不必要的外部动作，不提前给用户做状态性汇报。

## 当前最新本地证据
核查时间：2026-04-05 19:29:57 PDT

- 后台 wrapper 仍在运行：PID `47493`，PPID `1`
- 最新一轮关键产物刚刚刷新到 `2026-04-05 19:29:43 PDT`
  - `data/amazon-premium-wholesale/raw_candidates.json`
  - `output/amazon-premium-wholesale/latest.json`
  - `.logs/amazon-premium-wholesale-maintenance.log`
- `output/amazon-premium-wholesale/latest.json` 显示：
  - `input_mode: raw_input`
  - `post_family_dedupe_count: 36`
  - `candidate_count: 21`
  - `run_at: 2026-04-05T19:29:43.396369-07:00`

这说明当前背景链路不仅存活，而且就在刚才成功完成了新一轮刷新。

## 备选执行路径

### Plan A — 本地静默守护（最小干预）
**做法**
- 继续依赖现有后台 loop 自动运行
- 每次 runtime follow-up 仅做本地核查
- 只有出现 dead PID、stale mtime、fallback input mode、quality/backstop 异常、或接近报告窗口风险时才介入

**优点**
- 最符合“继续吧、全部做好再报告”
- 风险最低，不打断健康运行中的链路
- 完全符合 local-first 与安全边界要求

**缺点**
- 对“更大范围的 product-selection 最终闭环”推进有限
- 主要是守护现有成果，而不是扩展系统功能

### Plan B — 主动重启/重跑维护 loop
**做法**
- 停掉现有 wrapper 或手动再启动一份新实例
- 通过人工重跑验证当前轮次

**优点**
- 若当前进程异常，可快速恢复

**缺点**
- 当前没有异常证据，属于无必要干预
- 有打断健康链路、制造重复实例或锁冲突的风险
- 不符合“Protect device, data, and network first”与最小必要变更原则

### Plan C — 立刻推进更大 product-selection automation 闭环开发
**做法**
- 直接跳到日报、Excel、调度投递等后续未完工部分
- 将本次 follow-up 视作全面收尾的触发点

**优点**
- 若成功，可向最终目标推进一步

**缺点**
- 当前 runtime 任务更直接对应的是在跑的 Amazon premium wholesale 背景维护链路
- 现阶段没有新 blocker，贸然扩大范围会偏离“继续当前任务”的语义锚点
- 风险、改动面、验证成本都显著高于当前需要

## 选定计划
### 选定：Plan A — 本地静默守护（local-first safe execution）

**选择理由**
1. 与 runtime 已选 `local_first` 完全一致
2. 与本地 `amazon-premium-wholesale-maintenance-state.md` 的 next step 一致：
   - keep the existing background loop running without interruption
   - only intervene on dead/stale/failed-quality conditions
3. 有最新证据表明系统刚完成健康刷新，因此当前最优动作是“继续守护并验证”，而不是人为制造新变量
4. 安全边界最清晰：本地读验证为主，不做越权写操作，不做外部发送，不做高风险进程操作

## 执行门槛 / 介入条件
仅在满足以下任一条件时切换到修复性执行：
- PID 消失或 pidfile 指向无效进程
- `raw_candidates.json` / `latest.json` / log 的 mtime 明显停滞
- `input_mode` 不再是 `raw_input`
- 出现 failed quality、restore-last-good、或接近报告窗口的 material risk
- 输出结构不再满足当前最小可验证要求

## 当前计划下的下一步
进入 execute 阶段时：
- 继续做一次本地验证驱动的执行检查
- 将结果写入 execute checkpoint
- 若仍健康，则维持静默守护；若出现异常，再局部修复

## 安全结论
本计划：
- 不突破本地安全边界
- 不新增外部写操作
- 不引入无根据重启/重跑
- 保持设备、数据、网络优先安全
