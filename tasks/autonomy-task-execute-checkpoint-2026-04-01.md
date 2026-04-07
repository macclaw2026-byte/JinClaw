# autonomy-task · execute checkpoint · 2026-04-01

任务来源：background runtime execution request / task_id `autonomy-task`
阶段：execute

## 已完成执行
已把“任务产物文件优先直发到聊天对话框”逻辑落实到：
- `tools/openmoss/control_center/task_receipt_engine.py`

核心执行结果：
1. `emit_route_receipt(...)` 现在先提取附件，再优先调用 `_send_attachments_via_openclaw(...)`
2. 当附件发送成功时，不再追加重复的 session 文字回执
3. 只有在“没有附件”或“附件发送失败”时，才回退到 `_append_session_receipt(...)`
4. 回执记录增加 `delivery_strategy` 字段，用于标识投递策略

## 静态验证结果
- attachment_first_call=true
- fallback_only_on_failure=true
- suppressed_reason_present=true
- delivery_strategy_present=true
- `python3 -m py_compile` 通过

## 安全边界确认
- 仍沿用 `task_status_snapshot.py` 中的附件发现与过滤逻辑
- 仍限制为工作区内文件
- 仍排除 secrets/internal runtime 工件
- 仍限制在允许的文档/图片后缀白名单内
- 仍通过 OpenClaw 原生消息链发送，没有引入额外外发路径

## 目标完成度
用户要求的默认逻辑已实现：
- 后续这类任务只要能识别出可发送产物文件，就会优先直接发到聊天对话框中，用户可在对话框里直接打开
- 若无法直发，系统仍有文字回执兜底，不会静默失败
