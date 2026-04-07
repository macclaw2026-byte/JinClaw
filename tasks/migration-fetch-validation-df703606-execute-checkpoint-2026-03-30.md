# migration-fetch-validation-df703606 execute checkpoint

## 已完成动作

### 1. 已把 crawler 层“首次站点全工具评估 + 比对整理 + 站点记录”接入可执行代码
修改文件：
- `tools/openmoss/control_center/crawler_probe_runner.py`
- `tools/openmoss/control_center/crawler_layer.py`

本次新增的执行能力：
- 当任务目标含“第一次 / 首次 / 所有已知工具 / 全部工具 / all tools”等信号时，强制进入全工具评估模式
- 对每个工具结果增加假阳性识别：
  - login
  - captcha
  - robot / human verification
  - punish / nocaptcha / x5secdata
  - tiny output
  - shell without task fields
- 对每站结果做任务字段归一化
- 对工具结果做 arbitration score 排序
- 自动产出站点 profile：
  - markdown：`crawler/site-profiles/*.md`
  - json：`crawler/site-profiles/*.json`
- 自动写入长期学习偏好：`tools/openmoss/runtime/autonomy/learning/crawler_site_preferences.json`

### 2. 已基于这次测试结果重新落盘四站首批记录
已生成 / 更新：
- `crawler/site-profiles/amazon.json`
- `crawler/site-profiles/walmart.json`
- `crawler/site-profiles/temu.json`
- `crawler/site-profiles/1688.json`

并同步保留 markdown profile 文件：
- `crawler/site-profiles/amazon.md`
- `crawler/site-profiles/walmart.md`
- `crawler/site-profiles/temu.md`
- `crawler/site-profiles/1688.md`

### 3. 已落盘本任务的矩阵执行证据
- `tools/openmoss/runtime/autonomy/tasks/migration-fetch-validation-df703606/crawler_artifacts/crawler-tool-matrix.json`
- `tools/openmoss/runtime/autonomy/tasks/migration-fetch-validation-df703606/crawler_artifacts/crawler-tool-matrix-report.md`

## 当前核验到的结果

### Amazon
- 本次已记录为匿名公共抓取站点
- 当前 profile 中已跑到的工具列表包含：
  - `curl-cffi`
  - `local-agent-browser-cli`
  - `playwright`
  - `playwright-stealth`
  - `scrapy-cffi`
  - `crawl4ai-cli`
  - `direct-http-html`
- 当前排序结果首位：`curl-cffi`
- 说明：这反映的是当前归一化/排序实现下的最新自动结果，不再只是旧文档手写结论

### Walmart
- 当前匿名模式下仍主要表现为 human verification / robot 页面阻断
- 现有 JSON profile 中结论：`blocked_or_insufficient_evidence`
- 当前不应把 Walmart 视为已稳定拿到任务字段的站点

### Temu
- 当前 repeat-run 复核结果已稳定刷新：匿名模式最佳工具为 `local-agent-browser-cli`
- 最新执行证据：`crawler/reports/temu-latest-run.json` 与 `crawler/reports/temu-contract.json`
- 当前 contract 中结论：`best_tool=local-agent-browser-cli`，`best_status=usable`，`best_score=80`
- 当前保守结论：Temu 已具备“页面级稳定公开抓取”能力，但仍不应误写成“稳定商品级结构化字段全量抽取已完成”
- 说明先前“拿到大 HTML”不等于已经拿到可稳定任务字段，这一点现在已被执行器显式建模；本轮则进一步确认了页面级最佳工具与回退顺序

### 1688
- 当前匿名模式被明确标成：`anonymous_truth_check_only`
- 现有 JSON profile 中结论：`blocked_or_insufficient_evidence`
- 已记录的阻断/假阳性信号包括：
  - `x5secdata`
  - `captcha`
  - `punish`
  - `nocaptcha`
- 已把 1688 的授权登录模式写入结构化 policy：
  - `supported: true`
  - `mode: browser_authorized_session`
  - 需用户明确授权
  - 必须与匿名 profile 分离
  - 遇到 slider/captcha/device-risk 需要人工介入，不做绕过

## 关于“提供 1688 用户名和密码，工具自己登录，能不能实现”
当前执行结论：
- **可以实现“授权登录态模式”的工程框架**
- **不能承诺只要有用户名和密码，就能让所有工具稳定自动抓取**
- 正确实现方式应是：
  1. 用户明确授权
  2. 仅使用浏览器型工具建立一次正常登录态
  3. 把授权登录态作为独立 profile 记录
  4. 若出现 slider/captcha/device-risk，则保留人工介入
- 不应把原始账号密码分发给所有抓取栈轮流重放

## 仍存在的已知问题 / blocker
1. 这轮真正成功完成并落盘到 profile 的“全工具结果”，目前 Amazon 已经覆盖到 7 工具；但 Walmart / Temu / 1688 的最新 JSON 仍然显示来自一轮只命中了 3 个工具的执行结果，说明还需要再做一次严格 7 工具重跑，才能让四站结果完全同口径。
2. `crawler_probe_runner.py` 的字段归一化规则目前是启发式 regex 抽样，已经满足“有 compare/normalize contract”，但还不是针对各站生产级字段 schema。
3. retro 文件本轮尚未稳定落盘，需要下一次完整 probe 结束后补齐。

## 安全边界核验
- 未引入不明第三方黑盒抓取器
- 未尝试验证码/滑块绕过
- 未接收或存储任何真实账号密码
- 1688 登录态仅被建模为“可授权实现的浏览器流程”，未越过正常登录边界

## Done-definition 对齐情况
已满足：
- goal verified：已把首次站点全工具评估、比对整理、profile 记录接入执行器，并落盘四站记录
- security boundary preserved：未越过登录/验证码安全边界

仍待补齐：
- blockers resolved：四站同口径 7 工具重跑仍需完成
- final checkpoint written：本文件已写入

## 下一步最具体动作
- 用更新后的强制全工具逻辑，再对 Amazon / Walmart / Temu / 1688 执行一次严格 7 工具同口径 probe
- 产出完整 `crawler-retro.json`
- 再把 learning store 与四站 profile 同步到最终稳定排序
