# General Autonomy Runtime Design

## Goal

让当前 OpenClaw 从“能执行任务的代理”升级成“能持续推进任务直到真正达成目标的通用自治代理”。

目标能力：

- 自我判断
- 自我调度
- 自我恢复
- 自我反馈
- 自我总结
- 自我完善
- 自我进化
- 同类错误不重复犯

这不是某个专项 workflow，而是一层跨任务通用 runtime。

## Current reality

当前工作区已经存在以下雏形：

- `skills/continuous-execution-loop/`
- `skills/error-recovery-loop/`
- `skills/runtime-evolution-loop/`
- `skills/safe-learning-log/`
- `skills/self-cognition-orchestrator/`
- `tools/openmoss/bridge/`
- `tools/openmoss/voice/`
- `tools/openmoss/multitenant/`

问题不在于“完全没有能力”，而在于：

- 这些能力还分散在 skill 和 sidecar 中
- 缺一个统一的任务状态机
- 缺一个统一的观察/判断/执行/校验/恢复闭环
- 缺少跨任务的学习提升层
- 缺少“未达目标就继续，而不是输出一轮就停”的执行总线

## Core idea

不要把“通用自治”理解成一个 prompt。

它应该是 6 层结构：

1. Task Contract Layer
2. Execution State Machine Layer
3. Observation and Verification Layer
4. Recovery and Remediation Layer
5. Learning and Memory Promotion Layer
6. Runtime Evolution Layer

## 1. Task Contract Layer

每个长期任务都必须先被翻译成显式 contract。

contract 至少包含：

- task_id
- user_goal
- done_definition
- hard_constraints
- soft_preferences
- allowed_tools
- forbidden_actions
- checkpoint_policy
- retry_policy
- escalation_policy

没有 contract，就很容易出现：

- 误以为任务完成
- 遇到障碍就绕开
- 停在中间却没人知道

建议落盘位置：

- `tasks/runtime/<task_id>/contract.json`

## 2. Execution State Machine Layer

每个任务必须运行在统一状态机中，而不是一次 prompt 一次命令。

建议状态：

- `created`
- `planning`
- `running`
- `waiting_external`
- `blocked`
- `recovering`
- `verifying`
- `learning`
- `completed`
- `failed`

同时维护：

- current_stage
- attempts
- last_progress_at
- last_success_at
- blockers
- next_action
- evidence_refs

建议落盘位置：

- `tasks/runtime/<task_id>/state.json`

## 3. Observation and Verification Layer

这是把“我觉得做完了”变成“我能证明做完了”的关键层。

每个 stage 必须绑定：

- expected_output
- verification_method
- stale_timeout
- progress_signal
- failure_signal
- backstop_signal

验证方式必须外部化，不能只靠模型主观判断。

例如：

- 文件是否产生
- 页面是否真的出现目标数据
- API 是否返回预期结构
- 数据量是否达到阈值
- 目标指标是否满足

建议实现一个统一 verifier registry：

- `tools/openmoss/runtime/verifiers/`

## 4. Recovery and Remediation Layer

这是你最在意的地方：不能绕开问题，而要尽量解决问题。

恢复层需要明确区分：

- transient error
- environment error
- tool error
- auth/config error
- anti-bot / anti-scraping
- logic error
- wrong-plan error
- monitor miss

恢复动作不能只是“重试”，而应该是有层级：

1. retry same step
2. retry with stronger evidence
3. switch tool path
4. patch local workflow
5. request missing capability
6. escalate only if truly blocked

同时记录：

- root_cause_guess
- attempted_fixes
- successful_fix
- recurrence_risk

建议落盘位置：

- `tasks/runtime/<task_id>/recovery-log.jsonl`

## 5. Learning and Memory Promotion Layer

要做到“同样错误不犯第二次”，不能只写运行日志，必须做经验提升。

学习层分三种：

- task-local learning
- workflow-level learning
- runtime-level learning

### task-local

只影响当前任务。

例如：

- 这个网站需要先登录再抓
- 这个页面滚动到底才会加载数据

### workflow-level

适用于同类任务。

例如：

- 电商站点抓取优先走浏览器而不是静态请求
- 分页抓取后必须做去重校验

### runtime-level

适用于整个系统。

例如：

- 某类错误应该先检查权限位
- 某类长任务必须加 backstop monitor

建议落盘位置：

- `.learnings/LEARNINGS.md`
- `.learnings/ERRORS.md`
- `.learnings/reports/`
- `memory/`

## 6. Runtime Evolution Layer

“自我进化”不能等于随便改自己。

真正安全的 runtime evolution 应该是：

- 发现 recurring pattern
- 找到 fix 应该属于哪一层
- 生成提案
- 落成可审计变更
- 保留回滚路径

可以进化的对象：

- skill routing
- stage monitors
- shared verifiers
- bridge policy
- task templates
- retry policy
- logging policy
- memory promotion rules

不建议让系统无审计地直接改高风险核心文件。

## Missing piece in current project

当前最缺的是一个统一总线：

- `autonomy_runtime/manager.py`

它应该成为所有长期任务的 orchestrator。

## Proposed runtime components

建议新增：

- `tools/openmoss/autonomy/manager.py`
- `tools/openmoss/autonomy/task_contract.py`
- `tools/openmoss/autonomy/task_state.py`
- `tools/openmoss/autonomy/verifier_registry.py`
- `tools/openmoss/autonomy/recovery_engine.py`
- `tools/openmoss/autonomy/learning_engine.py`
- `tools/openmoss/autonomy/evolution_engine.py`
- `tools/openmoss/autonomy/checkpoint_reporter.py`

## Loop model

统一执行循环：

1. load task contract
2. inspect current state
3. choose next stage
4. execute action
5. verify result
6. if failed, enter recovery
7. if recovered, continue
8. if stage complete, checkpoint
9. extract learnings
10. promote durable improvements when justified
11. repeat until done_definition is satisfied

## Completion policy

任务不是“模型说完成了”就完成。

任务完成必须同时满足：

- stage graph fully resolved
- done_definition verified
- no critical blocker remains
- final report generated
- learnings persisted

## Why the current system is not enough yet

当前系统已经有：

- skill
- tool
- bridge
- memory
- recovery雏形

但还没有：

- 统一任务 contract
- 统一状态机
- 统一 verifier registry
- 统一 recovery engine
- 统一 learning promotion pipeline
- 统一 evolution gate

所以现在更像“有很多强组件”，还不是“完整自治 runtime”。

## Implementation phases

### Phase 1: Runtime skeleton

- task contract schema
- task state schema
- checkpoint writer
- manager loop skeleton

### Phase 2: Verification and recovery

- verifier registry
- recovery engine
- retry and branch rules
- blocker classification

### Phase 3: Learning and evolution

- worth-learning extractor
- recurrence detector
- promotion pipeline
- runtime change proposals

### Phase 4: Channel integration

- Telegram task entry
- bridge -> autonomy runtime
- voice summary hook
- multi-user runtime mapping

### Phase 5: True long-run autonomy

- watchdog / heartbeat integration
- stall detection
- delayed backstop review
- auto-resume after interruption

## Success criteria

实现完成后，一个通用长期任务应该具备：

- 接到目标后自动创建 contract
- 自动拆阶段并持续推进
- 中途失败自动分类和恢复
- 不把未解决问题伪装成完成
- 自动校验目标是否真达成
- 自动产出 checkpoint / summary
- 自动记录学习
- 对重复问题提出或应用改进

## Practical conclusion

你的想法可以实现，但它不是“再写一个 skill”。

它需要把当前已有的 skill 和 sidecar 收拢成一个统一自治运行时。

也就是说，下一步不是继续堆单点能力，而是：

先造 `general autonomy runtime`，
再让抓取、分析、研究、浏览器、语音、多用户这些能力都挂到这个 runtime 下面。
