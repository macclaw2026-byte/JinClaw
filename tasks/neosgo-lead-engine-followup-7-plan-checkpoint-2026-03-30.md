# neosgo-lead-engine-followup-7 plan checkpoint

日期：2026-03-30
任务来源：background runtime execution request / task_id `neosgo-lead-engine-followup-7`
阶段：plan

## 目标重述
在不突破安全边界的前提下：
1. 先修复此前提到的 CLI/runner 级问题
2. 把之前未纳入矩阵的 3 个渠道工具补进来，总计形成 7 个工具
3. 用 7 个工具对 4 个目标网站逐一抓取
4. 产出“每网站 × 每工具”的效果报告与测评结论

四个目标网站沿用当前本地证据链：
- Amazon
- Walmart
- Temu
- 1688

## 已核实的关键约束与证据

### 1. 已存在的五工具基础栈
来自 `tmp/crawler-bakeoff/run_stack_bakeoff_dual.py` 与既有 checkpoint：
- `official_api`
- `http_static`
- `scrapy_cffi`
- `crawl4ai_extract`
- `playwright_stealth`

### 2. CLI 问题已经被精确定位
核心问题不是“网站都失败”，而是 **runner 解释器选错**：
- `run_multisite_bakeoff.py` 之前使用 `sys.executable`
- 在当前调用环境下，`sys.executable` 指向系统 `python3`
- 系统解释器缺失 `httpx / playwright / crawl4ai / curl_cffi / selectolax` 等模块
- 因此多工具结果被污染成“环境级失败”，不是站点真实比较

已完成的低风险修正：
- `tmp/crawler-bakeoff/run_multisite_bakeoff.py` 已改为显式调用 `tools/crawl4ai-venv/bin/python`

这一步已经证明：
- 至少 `official_api / http_static / crawl4ai_extract / playwright_stealth` 可以放到受控解释器路径下运行
- 但 `scrapy_cffi` 仍受 `curl_cffi/selectolax` 所在环境影响，说明单一解释器并不能覆盖全部本地栈

### 3. 已核实的本地工具/环境现状
#### `crawl4ai-venv`
可用模块：
- `httpx`
- `playwright`
- `crawl4ai`
- `playwright_stealth`

缺失模块：
- `curl_cffi`
- `selectolax`

#### `matrix-venv`
可用模块：
- `curl_cffi`
- `scrapy`
- `playwright`
- `playwright_stealth`

缺失模块：
- `httpx`
- `crawl4ai`
- `selectolax`

#### 本地浏览器渠道工具
已确认存在且可调用：
- guarded `agent-browser` CLI
- OpenClaw 原生 `browser` 工具

这意味着补齐 7 工具时，不必引入新第三方安装；可以优先使用 **现有本地安全能力** 来扩容矩阵。

## 候选安全执行方案对比

### 方案 A：继续只修单个 runner，然后强行把 7 工具都塞进同一个 Python 环境
做法：
- 继续围绕单一 Python venv 打补丁
- 试图让全部 7 工具都共享一个解释器

优点：
- 结构看起来整齐
- Python 层统一

缺点：
- 当前本地并不存在一个已验证能同时覆盖全部能力的单一环境
- 若继续装包或重配环境，会扩大变更面
- 对 plan 阶段来说不是最低风险路径

安全判定：
- 中低风险，但变更面偏大

结论：
- 不选为首选方案

---

### 方案 B：保留五个 Python 栈，再补三种浏览器/HTTP 渠道工具，但临时手工跑，不做统一闭环
做法：
- 现有 5 栈继续用
- 补进 `agent-browser`、OpenClaw browser、raw/web fetch 等
- 手工整理结果

优点：
- 很快出结果
- 不必大改脚本

缺点：
- 容易遗漏
- 审计性、复跑性、对比一致性较差
- 与“每网站 × 每工具”正式报告目标不完全匹配

安全判定：
- 安全

结论：
- 可作为应急，不选为主方案

---

### 方案 C：构建一个新的本地 7 工具矩阵 runner，按工具选择已存在的安全执行通道（推荐）
做法：
1. 保留原有 5 个工具定义
2. 补入 3 个此前未正式纳入矩阵、但已在本地存在且可控的渠道工具
   - guarded `agent-browser` CLI
   - OpenClaw `browser` 工具
   - raw/web fetch 风格的轻量公开抓取通道
3. 不强求所有工具走同一个解释器，而是**每个工具绑定其已验证的本地执行通道**
4. 新建统一 matrix runner：
   - 输入：4 个网站
   - 输出：每网站 × 7 工具原始结果 + 统一评分 + 站点内排序 + 总结报告
5. 明确把“工具失败 / 站点阻断 / 可用结果”三类分开

优点：
- 最符合当前安全边界与现有资产
- 不依赖新增高风险安装
- 能真正完成“7 工具 × 4 网站”的比较要求
- 审计性强，可复跑

缺点：
- 需要新建一个更通用的 runner
- 评分标准要更明确，避免不同通道输出格式不一致

安全判定：
- 安全且最稳妥

结论：
- 选为主计划

---

### 方案 D：引入新的第三方抓取器/反检测链路来补足七工具
做法：
- 从外部再引入新 CLI / SaaS / 代理 / 反检测栈

优点：
- 可能提高个别站点成功率

缺点：
- 超出当前安全边界
- 计划阶段没有必要扩大供应链风险
- 与 in-house capability rebuild 不一致

安全判定：
- 不允许作为主路径

结论：
- 排除

## 选定主计划
选定：**方案 C：构建新的本地 7 工具矩阵 runner，按工具绑定安全执行通道**

原因：
1. 最符合用户要求：先修 CLI 问题，再补 3 个未测工具，总计 7 工具，逐站比较
2. 最符合当前本地实际：现有能力分布在多个受控环境与原生浏览器工具中
3. 不需要为了“统一环境”去做更高风险的依赖扩张
4. 可以把“工具本身失败”与“网站阻断/成功”严格区分，避免再次误判

## 推荐的 7 工具集合（计划草案）
基于当前已知本地能力，推荐矩阵中的 7 工具为：
1. `official_api`
2. `http_static`
3. `scrapy_cffi`
4. `crawl4ai_extract`
5. `playwright_stealth`
6. `agent_browser_cli`
7. `openclaw_browser`

说明：
- 这里不再把“授权会话”类高风险工具纳入本轮
- 也不依赖新的第三方安装
- 如需要保留一个更轻量纯 HTTP 对照组，可让 `http_static` 承担该角色，而不是额外扩容到第 8 个工具

## execute 阶段建议拆解

### E1. 固化 7 工具合同
- 定义每个工具的执行入口
- 定义统一输出字段：状态码、最终 URL、文本长度、命中信号、阻断信号、耗时、错误类型、预览

### E2. 构建 7 工具 runner
- 每个工具绑定到其已验证通道
- 任一工具失败不影响同站其它工具执行
- 结果统一落盘到 JSON

### E3. 执行 4 网站矩阵抓取
- Amazon
- Walmart
- Temu
- 1688

### E4. 统一评分与报告
- 每站内工具排序
- 明确区分：
  - usable / partial / blocked / tool_error
- 输出正式 markdown 报告与原始 JSON 证据

## 验证节点
### verify_goal
- 7 工具 × 4 网站全部有尝试结果
- 每网站都有每工具结论与推荐

### verify_security_boundary
- 不绕过登录/验证码/风控
- 不引入未审计高风险外部能力

### verify_approval_state
- 仅使用当前本地已存在且允许的能力
- 不需要新增危险批准

### verify_output_schema
- 原始 JSON 与最终报告一一对应
- 结论可回查

## 本阶段完成判定
已完成：
- 明确识别此前 CLI 问题的真实根因
- 比较多个安全执行方案
- 选定最合适的 in-house rebuild 路径
- 固化了 execute 阶段应采用的 7 工具矩阵思路

## 下一具体动作
下一步应立即进入 execute：
1. 新建统一 7 工具 matrix runner
2. 将 `agent_browser_cli` 与 `openclaw_browser` 纳入正式矩阵
3. 对四站跑完整矩阵
4. 生成正式报告与证据文件
