# Legacy Bridge Retired

这个目录原本承载 IMClaw / OpenMOSS bridge 旁路接入。

当前系统已经收敛为：

- 主聊天接入：OpenClaw 原生 `channels.telegram`
- 主执行链：OpenClaw gateway + JinClaw autonomy runtime

因此旧 bridge 运行链已经退役，不再参与：

- 收件
- 派发
- outbox 回发
- 运维体检主链

如果未来要增加新的聊天通道，请直接使用 `openclaw configure` 或 OpenClaw 原生 channel 机制，而不是恢复这套 bridge。
