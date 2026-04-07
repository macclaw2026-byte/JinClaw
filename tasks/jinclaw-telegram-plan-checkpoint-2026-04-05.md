# jinclaw-telegram — plan checkpoint

时间：2026-04-05 22:13 PDT

## 候选执行路径比较

### 方案 A：本地状态与健康探针优先（已选）
- 手段：使用 `openclaw status` 与 `openclaw status --deep`
- 优点：
  - 直接读取本机真实运行态
  - 不暴露密钥
  - 可获得 channel 状态、bot 探针、延迟等证据
  - 最符合 local-first 与安全边界
- 风险：
  - 主要验证到网关→Telegram provider 主链路，不覆盖所有业务层细节
- 适用性：最高

### 方案 B：直接检查配置与日志
- 手段：搜索本地配置、日志、Telegram 相关脚本/文档
- 优点：
  - 可补充架构上下文与异常线索
- 风险：
  - 容易只看到“配置存在”而非“链路真实可用”
  - 日志可能有时效偏差
- 适用性：中，适合作为辅证，不适合单独下结论

### 方案 C：外部 API / 公网读验证
- 手段：主动请求 Telegram Bot API 或其他公网检测
- 优点：
  - 可进一步独立确认外部可达性
- 风险：
  - 不必要扩大外部交互面
  - 可能涉及 token 使用边界
  - 当前本地健康探针已足够，无需升级到该方案
- 适用性：低，除非本地证据冲突或不足

## 选定方案
选择 **方案 A（本地状态与健康探针优先）**，并用方案 B 做少量辅证。

## 选择理由
- 满足 local-first safe execution
- 证据直接、可审计、低风险
- 已能证明 Telegram 通道当前为 `ON / OK`，深度探针为 `Telegram OK`
- 无 blocker，需要继续推进到执行/验证收口，而不是增加不必要的外部探测

## 已有验证证据（可供后续阶段复用）
- `openclaw status`：`Telegram ON / OK`
- `openclaw status --deep`：`Telegram OK`
- bot probe：`@JackenMac_Claw_bot:default:810ms`

## 下一步
在 execute/verify 阶段沿用该路径，必要时补充最近会话/链路侧证据，但不越过安全边界。
