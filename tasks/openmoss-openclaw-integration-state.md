# Task State

## Task
将 OpenMOSS 的关键能力融入当前 OpenClaw 工作区，并做成比 OpenMOSS 默认形态更强的本地能力体系

## Current Stage
阶段 2：完成代码级结构拆解并开始落本地集成骨架

## Completed Stages
- 扫描当前本地 OpenClaw 工作区结构
- 确认当前项目是工作区层，而非 OpenClaw 核心源码层
- 识别最相关 OpenMOSS 仓库：`imclaw-skill`、`OurClaw`、`MOSS-TTS`、`MOSS-TTSD`、`AnyGPT`
- 拉取并检查关键仓库的目录和核心脚本
- 建立本地集成项目目录与目标架构文档

## Pending Stages
- 创建 `imclaw-bridge-ops` 本地技能
- 创建 `moss-voice-orchestrator` 本地技能
- 增加本地 OpenMOSS 集成状态检查脚本
- 决定 vendor 布局与依赖管理方式
- 定义多模态 worker 契约
- 决定是否进入多用户隔离实现阶段

## Acceptance Criteria
- 当前工作区拥有清晰的 OpenMOSS 集成蓝图
- 至少具备 bridge / voice 两条能力线的本地技能骨架
- 有统一状态检查入口
- 有下一阶段实现顺序与验收口径

## Blockers
- 尚未把 OpenMOSS 运行时代码正式 vendor 到当前工作区
- 尚未决定 bridge / voice 是本地直接运行、容器运行，还是独立服务运行

## Next Step
- 新建本地 `imclaw-bridge-ops` 与 `moss-voice-orchestrator` 技能

## Last Updated
2026-03-21T10:25:00-07:00
