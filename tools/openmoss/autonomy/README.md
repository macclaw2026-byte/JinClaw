# General Autonomy Runtime

这层 runtime 的目标，不是替代 OpenClaw，而是给 OpenClaw 增加一套通用自治执行总线。

它负责：

- 任务 contract
- 状态机
- checkpoint
- 验证
- 恢复
- 学习
- 运行时进化提案

## Current files

- `manager.py`
- `task_contract.py`
- `task_state.py`
- `verifier_registry.py`
- `recovery_engine.py`
- `learning_engine.py`
- `checkpoint_reporter.py`
- `runtime_service.py`
- `task_ingress.py`
- `telegram_binding.py`

## Runtime data layout

任务状态写入：

- `tools/openmoss/runtime/autonomy/tasks/<task_id>/contract.json`
- `tools/openmoss/runtime/autonomy/tasks/<task_id>/state.json`
- `tools/openmoss/runtime/autonomy/tasks/<task_id>/events.jsonl`
- `tools/openmoss/runtime/autonomy/tasks/<task_id>/checkpoints/`

跨任务学习写入：

- `.learnings/LEARNINGS.md`
- `.learnings/ERRORS.md`
- `.learnings/reports/`
- `tools/openmoss/runtime/autonomy/learning/error_recurrence.json`
- `tools/openmoss/runtime/autonomy/learning/promoted_rules.json`
- `tools/openmoss/runtime/autonomy/learning/task_summaries/<task_id>.json`

## CLI

常用命令：

```bash
python3 manager.py create \
  --task-id demo-task \
  --goal "Continuously complete a long task" \
  --done-definition "All stages verified and final report written" \
  --stage "plan|Produce an execution plan" \
  --stage "execute|Run the plan" \
  --stage "verify|Verify the final outcome"

python3 manager.py status --task-id demo-task
python3 manager.py run-once --task-id demo-task
python3 manager.py complete-stage --task-id demo-task --summary "planning finished"
python3 manager.py fail-stage --task-id demo-task --error "tool timeout"
python3 manager.py checkpoint --task-id demo-task
python3 runtime_service.py --once
python3 task_ingress.py --goal "Continuously advance this task until verified complete"
```

## Design intent

这套 runtime 先把“长期任务不应该靠单轮 prompt 硬撑”变成工程事实。

后续 bridge、Telegram、voice、多用户隔离都应该挂到这层 runtime 上，而不是各自独立演化。

## Conflict policy

为避免“执行链”和“自治链”对同一任务重复动手，当前采用：

- `autonomy runtime` = supervisor / planner / verifier / recovery / learning
- `OpenClaw session` = single writer / single executor / external responder

也就是说：

- autonomy runtime 不直接对外回复 Telegram
- autonomy runtime 通过 `action_executor.py` 向绑定的 OpenClaw session 下发 stage 执行请求
- 执行痕迹会写入 `tasks/<task_id>/executions/`
- 派发后优先记录 `runId`，再由 watchdog 异步轮询完成状态，避免一次 `agent.wait` 超时就把长期任务卡住

## Learning loop

当前 runtime 已经会做三层沉淀：

- 任务级 summary：记录最近完成阶段、最近失败、验证结果、learning backlog
- 错误 recurrence：把同类错误归一化后跨任务累计
- promoted rules：当同类错误重复出现时，提升成 durable runtime rule，供 recovery 决策参考

## Stage Preflight

当前 preflight 已经不是单一通用判断，而是会按 guard 类型执行前置检查：

- `permission_error` -> 权限预检 / 目录可写性预检
- `missing_dependency` -> 路径预检 或 依赖命令预检
- `anti_automation_or_rate_limit` -> 节流 / 慢启动策略预检

这些 guard 会在 `action_executor.py` 真正派发 stage 之前运行。

## Telegram binding

可以通过显式前缀把 Telegram 消息直接绑定到 autonomy runtime：

- `/autonomy <goal>`
- `autonomy: <goal>`
- `持续任务: <goal>`

绑定会写入：

- `tools/openmoss/runtime/autonomy/ingress/telegram.jsonl`
- `tools/openmoss/runtime/autonomy/links/telegram__<chatId>.json`
