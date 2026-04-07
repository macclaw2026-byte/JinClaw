# neosgo-lead-engine-followup-8 execute checkpoint

## 已完成的本地能力重建与落盘

### 1. 已确认 crawler 层首轮判断逻辑文档存在并可执行
- 策略文件：`crawler/logic/crawler-decision-policy.md`
- 已覆盖：
  - 首次站点必须全工具跑一轮
  - 每个工具结果都要做 usable / partial / blocked / failed 分类
  - 先剔除 login / captcha / punish / empty shell 等假阳性页面
  - 再做归一化和任务字段对比
  - 输出任务需要的信息，而不是原始页面文本
  - 对已知站点记录首选工具和 fallback 顺序

### 2. 已确认四个站点的首批 profile 已写入
- `crawler/site-profiles/amazon.md`
- `crawler/site-profiles/walmart.md`
- `crawler/site-profiles/temu.md`
- `crawler/site-profiles/1688.md`

### 3. 已复核最近一次多站点 bakeoff 的真实证据
证据目录：`tmp/crawler-bakeoff/runs/20260330-062415/`

关键文件：
- `summary.json`
- `amazon.json`
- `walmart.json`
- `temu.json`
- `1688.json`

本轮结构上已执行的栈：
1. `official_api`
2. `http_static`
3. `scrapy_cffi`
4. `crawl4ai_extract`
5. `playwright_stealth`

### 4. 已重新核实四站当前更稳妥的结论

#### Amazon
- `crawl4ai_extract` 可用且最强
- 证据：`status_code=200`，markdown 约 `606196 chars`，html 约 `2728244 chars`
- 其余栈这次主要是环境缺模块，不是站点级优劣比较完成
- 当前可作为已知首选：`crawl4ai_extract`

#### Walmart
- `crawl4ai_extract` 命中 `Robot or human?` 验证页
- 证据：`status_code=307`，标题为 `Robot or human?`
- 当前更准确结论不是“可用但一般”，而是：匿名模式下当前路径被反爬拦截
- 本轮只能记录为：当前匿名抓取主结论 = `blocked`

#### Temu
- `crawl4ai_extract` 对首页可拿到较大 HTML
- 证据：`status_code=200`，html 约 `306917 chars`
- 但 markdown 只有 `301 chars`，说明“拿到页面”不等于“已经拿到高质量任务字段”
- 当前可以先记为：`crawl4ai_extract` 是已验证首选探针，但后续仍需做字段级归一化验证

#### 1688
- `crawl4ai_extract` 返回 `status_code=200` 且 html 较大，但 markdown 仅 `1 char`、title 为 `null`
- 这说明当前更像是拿到了前端壳、脚本壳或非任务可读内容，不能仅凭 HTML 体积判定为 strong
- 因此必须修正之前“1688 strong”的过度乐观结论
- 当前更稳妥结论：1688 匿名模式仍应视作 `unreliable / blocked-for-task-use`，尚不能当作稳定生产抓取路径

## 关于 1688 提供账号密码是否就能抓取
结论：**理论上可能帮助一部分登录后可见内容，但不能承诺“提供账号密码后几个工具就一定能自动抓到稳定数据”。**

原因：
1. 1688 的阻断不仅可能是账号登录门槛，还可能包括：
   - slider
   - captcha / nocaptcha
   - device-risk
   - punish / jump 页面
   - 登录后行为风控
2. 即使提供账号密码，也不应把原始凭证直接喂给所有抓取栈反复重放
3. 更安全、也更可控的实现方式应该是：
   - 仅在用户明确授权后
   - 使用浏览器型工具做一次正常登录流程
   - 把“已授权登录态抓取”视为与匿名模式完全分离的第二种站点 profile
   - 如果站点要求人工过 slider/captcha，则保留人工介入，不做绕过

所以答案是：
- **可以设计“授权登录态模式”**
- **但不能承诺无人工干预自动通过所有 1688 风控验证**
- **也不能把“有账号密码”直接等同于“所有工具都能稳定抓取”**

## 安全边界结论
- 本次仅复核本地已存在代码、策略和测试证据
- 未进行任何第三方不明工具导入
- 未尝试验证码/滑块绕过
- 未接收或使用任何真实账号密码
- 未突破本地或目标站点正常访问边界
- 安全边界保持完整

## 任务完成度判断
已完成：
- 明确了 crawler 层首次站点的全工具评估规则
- 确认了 Amazon / Walmart / Temu / 1688 四站的首批记录文件已经存在
- 对最新测试结果做了二次审校，修正了 1688 的错误乐观判断
- 明确了 1688 账号密码登录能力的真实边界和可实现方式

仍待后续实现的工程项：
1. 把 compare / normalize 真正接入执行脚本，形成自动产出任务字段
2. 把“匿名 profile”和“授权登录态 profile”分开建模
3. 在统一解释器环境下补齐依赖后，再做一次更公平的全栈 bakeoff

## 最终核验证据
- 策略：`crawler/logic/crawler-decision-policy.md`
- 四站 profile：`crawler/site-profiles/*.md`
- 运行证据：`tmp/crawler-bakeoff/runs/20260330-062415/summary.json`
- 状态文件：`tasks/crawler-layer-state.md`
