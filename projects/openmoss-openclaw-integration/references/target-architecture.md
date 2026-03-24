# Target Architecture

## North Star

优化后的当前 OpenClaw 项目，应该具备：

- 跨网通信能力
- 独立群聊 / 私聊上下文
- 高质量语音输出能力
- 可扩展的多模态任务入口
- 多用户隔离的未来扩展路径
- 比 OpenMOSS 默认实现更强的恢复、验证、审计、持续执行能力

## Layered Design

### Layer 1: OpenClaw orchestration

继续由当前工作区负责：

- 技能匹配
- 长任务状态
- 心跳 / cron / hook
- 错误恢复
- 记忆与学习
- 安全边界与审计

### Layer 2: OpenMOSS-derived capability adapters

新增适配层：

- IMClaw bridge adapter
- MOSS voice adapter
- multimodal worker adapter
- multi-user isolation adapter

这些层都不直接替代 OpenClaw，而是通过工具契约接入。

### Layer 3: External runtime services

需要时单独部署：

- IMClaw bridge process
- MOSS-TTS service
- MOSS-TTSD batch / dialog speech service
- AnyGPT worker

## Better-than-OpenMOSS Principles

### 1. Capability isolation

每个外部能力：

- 单独目录
- 单独状态文件
- 单独健康检查
- 单独恢复入口

### 2. External state first

不能只依赖聊天上下文。

至少要有：

- queue state
- processed archive
- runtime status
- task state
- health status

### 3. Stronger monitoring

每条链路必须明确：

- entry hook
- in-flight hook
- failure hook
- result-validation hook
- delayed backstop hook

### 4. Tool contracts

所有外部能力都应以统一输入输出契约暴露，不要把实现细节泄漏到上层技能。

### 5. Security

尤其注意：

- token
- cookies
- session state
- cross-user leakage
- browser auth state
- audio / image file retention

## Concrete Near-Term Build Order

1. `imclaw-bridge-ops`
2. `moss-voice-orchestrator`
3. `openmoss-integration-status`
4. `multimodal-worker` contract draft
5. `ourclaw-style-user-isolation` draft
