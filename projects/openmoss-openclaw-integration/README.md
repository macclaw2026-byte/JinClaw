# OpenMOSS x OpenClaw Integration

这个项目目录用于把 OpenMOSS 体系里的强能力，转化成当前本地 OpenClaw 工作区可以长期维护、逐步上线、可验证的能力层。

## 目标

不是把 OpenMOSS 原样搬进来。

而是把最有价值的能力拆成适合当前工作区的几层：

- `IMClaw bridge layer`
- `MOSS voice layer`
- `multimodal worker layer`
- `multi-user isolation layer`
- `benchmark + evaluation layer`

## 当前结论

最值得优先吸收的 OpenMOSS 仓库：

- `OpenMOSS/imclaw-skill`
- `OpenMOSS/OurClaw`
- `OpenMOSS/MOSS-TTS`
- `OpenMOSS/MOSS-TTSD`
- `OpenMOSS/AnyGPT`

不建议第一阶段直接替换主推理模型为 `OpenMOSS/MOSS`。

原因：

- 当前本地工作区已经以 OpenClaw 技能图 + 浏览/研究工具为主
- 先接入通信、语音、多模态入口，收益更快
- 主模型替换成本最高、验证面最广、风险也最大

## 分阶段路线

### Phase 1: IMClaw bridge

目标：

- 让当前 OpenClaw 工作区具备跨网实时通信能力
- 每个群聊 / DM 独立 session
- 入站消息队列化
- wake/hook/cron 与主 session 联动

产物：

- `skills/imclaw-bridge-ops/`
- `tools/openmoss/bridge/`
- 本地状态文件 + 队列目录规范

### Phase 2: MOSS voice

目标：

- 把 `MOSS-TTS` 与 `MOSS-TTSD` 接入到 OpenClaw 回复链路
- 支持语音摘要、长文播报、多角色汇报

产物：

- `skills/moss-voice-orchestrator/`
- `tools/openmoss/voice/`
- 语音生成输入/输出契约

### Phase 3: Multimodal worker

目标：

- 以独立 worker 方式吸收 `AnyGPT`
- 提供统一的多模态任务入口，而不是把 AnyGPT 混进主 runtime

产物：

- worker service contract
- request / response schema
- image / audio / speech / text routing rules

### Phase 4: Multi-user isolation

目标：

- 借鉴 `OurClaw` 的 shared-template + per-user runtime 结构
- 保留共享技能，同时隔离 `USER.md`、记忆、配置、日志

产物：

- common workspace template
- per-user config generation strategy
- relay / routing strategy

### Phase 5: Better-than-OpenMOSS

目标：

- 在 OpenMOSS 的基础上做更强的工作流编排与验证
- 不只是“有能力”，还要“更稳定、更可控、更可追踪”

重点增强：

- 更强的 hook/backstop/恢复机制
- 更清晰的任务状态文件
- 更好的技能审计与安全边界
- 更完整的 benchmark 和回归验证

## 当前工作区如何承接这些能力

当前本地项目的优势：

- 已有技能图
- 已有浏览器工具与 Crawl4AI
- 已有记忆 / 心跳 / 持续执行 / 恢复 / 自演化机制

所以最正确的接法是：

- OpenMOSS 提供“外部能力模块”
- 当前工作区提供“调度、监控、恢复、记忆、审计、长期维护”

## 下一步

1. 完成 `imclaw-bridge-ops` 技能骨架
2. 完成 `moss-voice-orchestrator` 技能骨架
3. 增加本地 `openmoss-integration-status` 检查脚本
4. 明确 vendor 布局和运行时依赖
5. 再决定是否要把 OpenMOSS 仓库 vendor 到当前工作区
