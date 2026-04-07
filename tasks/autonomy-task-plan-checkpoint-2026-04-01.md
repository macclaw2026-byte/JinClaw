# autonomy-task · plan checkpoint · 2026-04-01

任务来源：background runtime execution request / task_id `autonomy-task`
阶段：plan

## 用户目标
把任务产物文件直接发到聊天对话框中，让用户能在聊天对话框里直接打开；并把后续这类任务默认改成这种逻辑。

## 已比较的安全执行方案

### 方案 A：仅把文件路径写进文字回执
- 优点：改动最小。
- 缺点：用户仍需要手动去文件系统找文件，不能满足“直接发到聊天对话框”的目标。
- 结论：不选。

### 方案 B：继续先写 session 文字回执，再额外发附件
- 优点：兼容旧行为。
- 缺点：聊天里会出现重复回执；用户体验差，而且容易让人误以为系统发了两次。
- 结论：不选。

### 方案 C：识别到可发送附件时，优先原生聊天附件直发；仅在失败时回退文字回执
- 优点：直接满足目标；不破坏安全边界；保留失败回退；兼容现有 attachment discovery。
- 风险：需要确保不会在附件已发送成功时继续重复追加 session 文字回执。
- 结论：已选定，为当前最佳路径。

## 已执行的具体改动
- 修改 `tools/openmoss/control_center/task_receipt_engine.py`
- 调整 `emit_route_receipt(...)`：
  1. 先抽取 `output_attachments`
  2. 有附件则先走 `_send_attachments_via_openclaw(...)`
  3. 仅当附件投递失败或没有附件时，才 `_append_session_receipt(...)`
- 新增回执记录字段：`delivery_strategy`
  - `native_chat_attachment_first`
  - `session_receipt_only`

## 安全边界检查
- 仍然只发送 `_attachment_candidates_from_route(...)` 与 `task_status_snapshot.py` 已过滤后的工作区文件。
- 未放宽附件后缀白名单。
- 未放宽工作区路径限制。
- 未新增任何越权网络通道；仍使用 OpenClaw 原生消息发送链。

## 验证证据
- `python3 -m py_compile tools/openmoss/control_center/task_receipt_engine.py` 通过
- 导入校验通过：模块可加载，`emit_route_receipt` 存在

## 当前选定计划
采用方案 C：附件优先直发聊天窗口，失败时回退文字回执。
