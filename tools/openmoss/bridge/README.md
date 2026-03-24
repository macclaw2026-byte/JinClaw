# OpenMOSS Bridge Runtime

这个目录预留给本地的 IMClaw / OpenMOSS bridge 运行时。

建议后续放入：

- `bridge_runner.py`
- `process_queue.py`
- `reply_router.py`
- `bridge_status.json`
- `queue/`
- `processed/`
- `sessions/`
- `group_settings.yaml`

## 目标

把 `OpenMOSS/imclaw-skill` 的能力做成适合当前 OpenClaw 工作区的本地运行时。

## 原则

- 运行时与技能说明分离
- 状态外置
- 回复链可验证
- 错误可恢复
- 安全边界明确
