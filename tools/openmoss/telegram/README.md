# Telegram-Native OpenMOSS Layer

这个目录用于把 OpenMOSS 的核心能力直接接到当前 OpenClaw 的 Telegram 通道上，而不是依赖 IMClaw。

当前方向：

- 复用 OpenClaw 现有 Telegram channel
- 保持每个 Telegram chat 独立 session
- 通过 sidecar 增加：
  - 额外编排
  - 语音生成
  - 多用户隔离
  - 后续多模态 worker

关键原则：

- 不替换 OpenClaw 自带 Telegram provider
- 只增强现有 Telegram 会话能力
- Telegram group 直接映射到 `agent:main:telegram:group:<chatId>`
