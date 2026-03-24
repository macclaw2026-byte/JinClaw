# Safe Rollout

这套 bridge 运行时默认是旁路模式，不会自动接管当前 OpenClaw。

## 当前安全策略

- 默认 `enabled=false`
- 默认 `dry_run=true`
- 状态只写入：
  - `tools/openmoss/runtime/bridge/`
- 不自动改写：
  - `~/.openclaw/openclaw.json`
  - 当前 gateway
  - 当前 Telegram / browser / cron 运行链

## 启用顺序

1. `bridge_runner.py init`
2. `bridge_runner.py status`
3. `bridge_runner.py ingest-sample ...`
4. `process_queue.py`
5. `dispatch_to_openclaw.py`
6. `reply_router.py ...`
7. `deliver_outbox.py`
8. `bridge_service.py --once --no-live-transport`
9. 确认状态文件和 dispatch/outbox 行为正确
10. 再考虑接真实 IMClaw transport

## 真实接入前的要求

- token 和 transport 配置单独放
- token 可来自环境变量或 `tools/openmoss/bridge/.env.local`
- 真实发送必须先从 `dry_run` 改成显式启用
- 真实 wake 不应直接影响当前主系统，先通过独立调试入口验证
- 真实 OpenClaw dispatch 必须只发往独立 `session_key`
- 真实 IMClaw 回发必须先验证 `deliver_outbox=true` 的小流量链路
