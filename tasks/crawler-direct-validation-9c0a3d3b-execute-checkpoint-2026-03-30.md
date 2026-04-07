# crawler-direct-validation-9c0a3d3b execute checkpoint

## 本轮实际执行

### 1. 核验并固化 crawler 层首次站点判断逻辑
已核验现有可执行入口：
- `crawler/logic/crawler_runner.py`
- `crawler/logic/crawler_contract.py`
- `crawler/logic/crawler-decision-policy.md`

本轮补强点：
- 新增显式首次站点状态文件：`crawler/state/first_run_state.json`
- 修改 `crawler_runner.py`：
  - 不再只靠“有没有 profile”判断是否做首次全工具评估
  - 改为：若站点尚未被标记完成首次评估，则即使已有 profile，也仍强制执行全工具评估
  - 当完成一次全工具评估后，自动写入首次评估完成状态

这让“第一次一定要跑所有已知工具，再比对、整理、记录优先顺序”的规则从文档约定，变成了有状态保障的执行逻辑。

### 2. 已确认四个站点当前的首批记录文件都存在
已存在并可继续作为当前基线：
- `crawler/site-profiles/amazon.md`
- `crawler/site-profiles/walmart.md`
- `crawler/site-profiles/temu.md`
- `crawler/site-profiles/1688.md`
- `crawler/site-profiles/amazon.json`
- `crawler/site-profiles/walmart.json`
- `crawler/site-profiles/temu.json`
- `crawler/site-profiles/1688.json`

对应运行/合同证据也已存在：
- `crawler/reports/amazon-latest-run.json`
- `crawler/reports/walmart-latest-run.json`
- `crawler/reports/temu-latest-run.json`
- `crawler/reports/1688-latest-run.json`
- `crawler/reports/amazon-contract.json`
- `crawler/reports/walmart-contract.json`
- `crawler/reports/temu-contract.json`
- `crawler/reports/1688-contract.json`

### 3. 当前四站基线结论（来自已落盘结果，而非口头推断）

#### Amazon
- 已记录为可做匿名公共抓取
- 当前最佳工具：`local-agent-browser-cli`
- 已知更强路径主要集中在浏览器渲染 / 浏览器型结果
- `playwright` / `playwright-stealth` 在当前样本里触发了 Amazon 错误页

#### Walmart
- 当前大量结果仍落到 human verification / robot 页面
- 站点不应被视为“稳定匿名生产抓取已打通”
- 需要继续把字段级任务输出与反爬阻断明确区分

#### TEMU
- 当前记录显示 `local-agent-browser-cli` 是唯一清晰可用主路径
- 其他路径多为 shell-heavy / partial / blocked
- 说明匿名可用，但强依赖浏览器型路径

#### 1688
- 当前匿名模式仍应视为 blocked / truth-check-only
- 已有记录明确命中：登录页、滑块、punish、x5secdata、nocaptcha 等阻断信号
- 不能把匿名 profile 误判成可稳定生产抓取路径

### 4. 关于 1688 提供用户名密码后“工具自己登录，能不能实现”
执行结论：
- **可以实现“授权登录态浏览器流程”**
- **不能承诺只要有账号密码，就能让所有工具无人值守稳定抓取**

正确边界：
1. 需要 Jacken 明确授权
2. 仅在浏览器型工具里执行一次正常登录
3. 登录态与匿名态必须分开记录为不同 profile / run history
4. 如出现 slider/captcha/device verification，暂停并要求人工完成，不做绕过
5. 不把原始用户名/密码广播给所有 crawler 栈轮流重放

已存在并继续有效的策略文件：
- `crawler/site-profiles/1688-auth-policy.md`

## 安全边界核验
- 未引入未知第三方黑盒能力
- 未尝试验证码/滑块/风控绕过
- 未接收、写入或传播任何真实账号密码
- 1688 仅被建模为“可授权的浏览器登录流程”，而不是“可无条件自动攻破的抓取站点”

## 仍待完成的 blocker
1. 还缺一轮**严格同口径的四站全工具重跑证据**，用于把四站 profile 再统一刷新到同一轮 matrix 基线之上。
2. 当前字段归一化仍偏启发式，需要后续按任务字段 schema 做更精细规范化。
3. 还缺一个汇总型 retro 文件，把 Amazon / Walmart / TEMU / 1688 四站的工具优先级、失败模式、后续策略统一汇总。

## 下一步最具体动作
- 运行一次新的四站严格全工具 matrix probe
- 重新刷新四站 profile / latest-run / contract
- 产出统一 retro 文档（建议文件名：`crawler/reports/crawler-retro.json`）

## 简要核验证据
- 规则文档：`crawler/logic/crawler-decision-policy.md`
- 执行入口：`crawler/logic/crawler_runner.py`
- 显式首次状态：`crawler/state/first_run_state.json`
- 四站 profile：`crawler/site-profiles/*.md` / `*.json`
- 四站运行证据：`crawler/reports/*-latest-run.json`
- 1688 授权登录边界：`crawler/site-profiles/1688-auth-policy.md`
