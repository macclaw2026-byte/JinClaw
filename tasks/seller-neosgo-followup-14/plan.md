# seller-neosgo-followup-14 执行方案（plan stage）

生成时间：2026-04-01 10:18 PDT

## 一、已验证的本机现状

### 1) 数据库已存在且已落地
- 数据库路径：`/Users/mac_claw/.openclaw/workspace/data/neosgo_leads.duckdb`
- 已存在核心表：
  - `raw_import_files`
  - `raw_contacts`
  - `normalized_contacts`
  - `deduped_contacts`
  - `scored_prospects`
  - `persona_summary`
  - `outreach_ready_leads`
  - `outreach_queue`
  - `outreach_events`
  - `campaign_variants`

### 2) Downloads 中压缩包导入情况已核实
- `~/Downloads` 下共发现 ZIP 压缩包：16 个
- ZIP 内 CSV 成员总数：96 个
- 已导入数据库的 CSV 成员数：96 个
- 缺失未导入成员数：0 个

结论：**“把所有用户数据全部导入本机数据库”这一步，目前已基本完成。**

### 3) 当前数据规模（已核实）
- `raw_import_files`: 96
- `raw_contacts`: 67,382,866
- `normalized_contacts`: 67,382,866
- `deduped_contacts`: 40,800,031
- `scored_prospects`: 40,422,503
- `outreach_ready_leads`: 2,391,788
- `outreach_queue`: 2,976,361
- `outreach_events`: 3

### 4) 当前已跑出的部分结果
高价值细分人群已经能从本地规则模型中筛出，样本量较大的 segment 包括：
- contractor
- realtor
- electrician
- hospitality
- furniture_retailer
- architect
- builder
- designer
- lighting
- kitchen_bath

S/A 潜客集中州包括：
- FL
- CA
- NY
- TX
- IL
- NJ
- OH
- PA
- VA
- NC

## 二、推荐执行路径（最终选择）

### 选定方案：In-house capability rebuild
原则：**不依赖高风险第三方黑盒能力，保留有价值的方法论，全部在本机重建、可解释、可审计、可持续迭代。**

这是当前最稳妥、最适合长期跑自动化的一条路，原因：
1. 现有本地数据库和 DuckDB 仓库已经建立，继续沿用成本最低。
2. 已有导入、标准化、去重、打分、日报脚本，可直接扩展，而不是推倒重来。
3. 所有逻辑都能版本化与复盘，方便后续按真实转化数据优化。
4. 免费工具即可覆盖绝大部分能力。

## 三、理想可行方案（按阶段）

## Phase 0：基线确认与资产固化
目标：把“现在已有的半成品”正式固化成可持续运行的 lead engine。

动作：
1. 固化数据库 schema 与视图说明。
2. 把当前脚本整理成标准工作流：
   - 导入
   - 标准化
   - 去重
   - 打分
   - 队列生成
   - 日报生成
3. 增加任务状态文件、运行日志、失败重试机制。
4. 输出一版数据字典与字段映射文档。

产出：
- 稳定版 lead-engine 目录结构
- runbook
- 数据字典
- 首版日报模板

## Phase 1：潜客筛选算法升级
目标：让“谁最像 Neosgo 潜在客户”这件事更准，而且可解释。

### 当前可用的筛选逻辑（已实现雏形）
现有模型是 explainable scoring model，满分 100，主要由以下几部分构成：
1. **行业匹配度（0-30）**
   - 室内设计 / 设计事务所
   - 建筑师 / 建筑设计
   - Builder / Developer
   - General Contractor / Remodeler
   - Electrician / Lighting installer
   - 家具零售 / kitchen bath / hospitality / property 管理等
2. **决策影响力（0-20）**
   - Owner / Founder / Principal / President / Partner
   - Director / Manager / Purchasing / Procurement
   - Designer / Architect / Project roles
3. **企业规模与商业价值（0-15）**
   - 员工规模分段
   - 公司体量
4. **Neosgo 适配度（0-20）**
   - 是否像 trade buyer / channel buyer / influencer
5. **可触达性（0-10）**
   - 是否有有效邮箱、电话、网站、明确联系人
6. **重点市场加权（0-5）**
   - CA / TX / FL / NY / NJ / IL / WA / GA / NC / VA / MA 等州

### 建议升级为“双层筛选模型”

#### 第一层：规则过滤（高召回）
先做硬过滤，排掉明显无价值对象：
- 无邮箱或邮箱明显无效
- 无网站
- 联系方式严重缺失
- 行业完全无关
- 公司主体不清晰
- 重复主体

#### 第二层：精细打分（高精度）
在候选集上做细分加权：
- 行业是否与灯饰、家具、家居、项目采购、室内方案、施工交付相关
- 是否具备“推荐权”“采购权”“影响业主选品”的身份
- 是否处于项目链条关键节点
- 是否更像长期合作客户而不是一次性散客
- 是否可能在线下成交或网站成交

### 潜在客户画像（建议版）

#### Persona A：室内设计/建筑设计事务所
- 典型职位：Principal Designer / Owner / Interior Designer / Architect
- 特征：有项目选品权、影响客户审美和品牌选择、可持续复购
- 价值：高客单、高复购、高推荐可能

#### Persona B：Builder / Contractor / Remodeler
- 典型职位：Owner / Project Manager / Purchasing / Estimator
- 特征：项目型采购，重视供货稳定、价格、交付、配套能力
- 价值：可做项目批量成交和持续补货

#### Persona C：Electrician / Lighting contractor / Installer
- 典型职位：Owner / Lead Electrician / Operations Manager
- 特征：在灯具安装链路中有强影响力，可推荐或打包采购
- 价值：适合转介绍、工程安装绑定、局部批量单

#### Persona D：家具/家居零售商、showroom、kitchen & bath
- 典型职位：Owner / Buyer / Merchandising / Purchasing
- 特征：适合渠道合作、样品合作、批发分销
- 价值：更适合批发与陈列合作

#### Persona E：房地产经纪/物业/酒店/多户住宅管理
- 典型职位：Broker / Property Manager / Hospitality procurement
- 特征：可带来 staging、翻新、样板房、酒店/公寓采购场景
- 价值：转介绍和项目单价值较高，但筛选要更谨慎

## Phase 2：营销策略设计
目标：不是“群发”，而是按人群做不同价值主张。

### 核心原则
1. 分人群，不同话术
2. 先价值、后成交
3. 先小转化，再大成交
4. 线上与线下并行
5. 所有触达都可追踪、可归因、可优化

### 细分策略

#### 1. 设计师/建筑师
主打：
- trade pricing
- 项目报价响应速度
- 定制化选品支持
- 样品与方案协作
- 提升客户项目效果与利润空间

CTA：
- 预约 15 分钟 fit call
- 获取 trade catalog / quote support
- 提交项目需求拿报价

#### 2. Builder/Contractor
主打：
- 稳定供应
- 项目配套
- 批量价格
- 交付效率
- 售后配合

CTA：
- 提交当前项目清单
- 申请批量报价
- 约一个项目适配沟通

#### 3. Electrician / lighting installers
主打：
- 易安装产品
- 项目配套补货
- 推荐佣金/合作机制（若业务允许）
- 现场需求响应

CTA：
- 看安装友好型产品清单
- 推荐合作政策沟通

#### 4. 渠道客户（家具店/showroom/kitchen&bath）
主打：
- 差异化产品线
- 经销/批发利润空间
- 供货稳定性
- 样品陈列合作

CTA：
- 申请批发价目
- 申请样品/目录
- 渠道合作沟通

## Phase 3：客户开发方案（从营销到成交）

### 漏斗设计
1. 数据入库
2. 评分筛选
3. 分群
4. 生成话术与外呼队列
5. 首触达
6. 跟进
7. 识别高意向
8. 推动网站下单或线下成交
9. 回写结果
10. 用结果优化模型

### 推荐开发动作链

#### 路径 A：邮件开发
- Day 1：首封价值型邮件
- Day 3：补充案例/产品利益点
- Day 7：跟进提醒
- Day 12：最后一次低打扰跟进

#### 路径 B：网站转化
- 邮件/LinkedIn/电话把人导向：
  - trade account 申请页
  - quote request 页
  - catalog 下载页
  - contact us / WhatsApp 咨询页

#### 路径 C：线下成交
适用于 builder、designer、dealer、hotel、property 类客户：
- 先拿到项目需求
- 再做报价/样品/目录
- 最后推动电话会、视频会或线下拜访

### 状态设计（CRM 最小闭环）
推荐至少维护：
- pending
- scheduled
- sent
- opened
- clicked
- replied
- qualified
- quote_requested
- sample_requested
- meeting_booked
- won
- lost
- do_not_contact

## Phase 4：持续自动执行与自我迭代
目标：系统每天自己跑，并根据真实反馈优化。

### 自动化闭环
1. 每天扫描是否有新压缩包/新 CSV
2. 增量导入数据库
3. 重建去重与打分层
4. 生成当天新增高分潜客
5. 生成分群开发队列
6. 读取 outreach 反馈事件
7. 根据回复率/询盘率/报价率/成交率调整：
   - segment 权重
   - title 权重
   - state 权重
   - 文案版本优先级
   - 触达节奏
8. 输出日报

### 自我优化的核心不是“自动乱学”，而是“受控迭代”
建议采用：
- 版本化评分规则
- A/B 文案版本
- 每周人工复盘一次
- 满足最小样本量后再调整权重

## Phase 5：每日汇报机制
日报建议固定输出：
1. 新导入数据量
2. 去重后有效联系人数
3. 新增 S/A 潜客数
4. 各细分人群新增量
5. 已触达数量
6. 回复数量
7. 报价/样品/会议/成交数量
8. 当前阻塞项
9. 下一步动作

本机已经有日报脚本：
- `skills/neosgo-lead-engine/scripts/generate_daily_report.py`

并已生成今日样例：
- `/Users/mac_claw/.openclaw/workspace/reports/neosgo/daily-report-2026-04-01.md`

## 四、实现这套方案需要的条件

## A. 我现在已经能自己解决的（免费）
1. **本地数据库层**：DuckDB 已有
2. **批量导入**：已有脚本可用
3. **去重与打分**：已有基础脚本可迭代
4. **日报生成**：已有脚本可用
5. **任务编排**：可用本地脚本 + cron 完成
6. **本地文档与策略沉淀**：我可以直接搭建

## B. 要真正“自动开发客户”，还缺这些关键能力
下面这些不是数据库和算法本身，而是“触达世界”的能力。

### 1. 邮件发送能力（必需，若走邮件开发）
需要至少一种：
- Gmail / Google Workspace SMTP
- Amazon SES（付费，不优先）
- Resend / Brevo / Mailgun 免费层（优先考虑免费层）

如果没有发信能力，就只能先生成开发名单和文案，不能真正批量开发。

### 2. 邮件追踪/回复回流（强烈建议）
需要拿到：
- sent
- reply
- bounce
- maybe open/click

最省事方式：
- 用一个能提供 webhook 或日志导出的邮件服务
- 或者接入一个专门用于销售开发的邮箱工具

### 3. 网站承接页/表单（强烈建议）
为了提升转化，最好有：
- trade account 申请页
- quote request 页
- catalog/download 页
- 联系我们/WhatsApp 表单

没有承接页，触达后转化路径会很弱。

### 4. CRM 或至少一个外联事件回写入口（建议）
最简可以先用本地 DuckDB + CSV 回写。
更理想是未来接：
- Airtable 免费层
- Notion database
- Google Sheets
- 或继续完全本地化

### 5. 合法合规边界（必须）
开发前必须确认：
- 发信域名与邮箱准备好
- 有退订机制或最少合规说明
- 不要高频群发导致域名受损
- 遵守目标市场的开发邮件规范

## C. 如果 Jacken 愿意配合，我需要你帮我补的东西
优先级从高到低：

### P1（最关键）
1. 一个可用的外联邮箱/发信通道
2. Neosgo 的核心卖点素材：
   - 产品范围
   - 价格优势
   - trade account 机制
   - 是否支持样品/报价/佣金/批发
   - 典型案例
3. 最终希望引导客户去哪里成交：
   - 网站链接
   - 表单页
   - WhatsApp
   - 邮箱
   - 电话

### P2（强烈建议）
4. 一套基础营销素材：
   - company intro
   - 产品目录
   - 常见问题
   - 开发对象的案例图/图片
5. 是否允许做多渠道开发：
   - 邮件
   - LinkedIn
   - 电话
   - WhatsApp

### P3（优化项）
6. 一份“哪些客户绝对不要碰”的排除规则
7. 一个你认可的目标州/目标行业优先级清单
8. 成交定义：
   - 网站注册
   - 提交询盘
   - 索样
   - 约会议
   - 首单

## 五、推荐的最小可行落地版本（MVP）

### MVP-1：一周内能跑起来的版本
1. 固化导入与日报
2. 升级评分逻辑
3. 生成 Top 10,000 高分潜客池
4. 为 3 个核心人群产出 3 套邮件文案
5. 建立本地 outreach 事件回写结构
6. 每天自动生成进展汇报

### MVP-2：真正开始开发客户的版本
在 MVP-1 基础上增加：
1. 接入发信能力
2. 先小批量发送（每日 50~200）
3. 回写 sent/reply/quote_request
4. 用结果调整模型和文案

### MVP-3：持续优化版本
1. 分州/分行业/分角色优化权重
2. A/B test 文案
3. 引入 website / CRM / WhatsApp 承接
4. 按成交结果做闭环优化

## 六、我建议现在的具体下一步

最优先的下一步不是继续空谈，而是直接进入下面顺序：

1. **把现有 neosgo lead engine 目录整理成正式技能/项目结构**
2. **补一版更完整的潜客评分逻辑与画像说明文档**
3. **设计营销策略文档与客户开发 SOP**
4. **定义 outreach 反馈数据结构**
5. **接每日 cron 报告**
6. **如果你给我发信通道，我就能继续往“自动开发客户”推进**

## 七、当前阶段结论

- 用户要求的第 1 项（把 Downloads 里的用户数据导入数据库）已经核实完成。
- 第 2~6 项已经有可复用基础设施，但要做成真正长期稳定的客户开发系统，还需要把“评分逻辑、营销策略、开发动作、反馈闭环、日报自动化”正式产品化。
- 这条路**完全可以免费优先启动**；真正可能需要你协助的，主要是**发信通道、Neosgo 营销素材、成交承接页/入口**。
- 当前最安全、最可持续的方案就是：**继续走本机重建、可解释、可审计、可迭代的 in-house capability rebuild 路线。**

## 八、验证证据（concise verification evidence）
- 已发现本机 DuckDB：`data/neosgo_leads.duckdb`
- 已核实 Downloads ZIP：16 个
- 已核实 ZIP 内 CSV 成员：96 个
- 已核实已导入成员：96 个
- 缺失成员：0 个
- 今日日报样例已生成：`reports/neosgo/daily-report-2026-04-01.md`
- 本次计划文档已写入：`tasks/seller-neosgo-followup-14/plan.md`
