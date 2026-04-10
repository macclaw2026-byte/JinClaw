# Amazon Product Selection 执行方案

更新时间：2026-04-10 12:28 PDT

## 一、任务目标

在 JinClaw/OpenClaw 内建立一条可持续执行的亚马逊选品工作流，分阶段完成以下事情：

1. 从卖家精灵拿到首轮候选产品数据
2. 对候选产品提取主要关键词
3. 去亚马逊前台按关键词采集竞争信息
4. 以关键词维度整理出可筛选、可导出的结果表

## 二、治理锚点

这个任务不是临时脚本，而是本机 `openclaw` 任务框架的一部分，必须显式对齐 JinClaw 的三层框架：

- 宪法层：`/Users/mac_claw/.openclaw/workspace/JINCLAW_CONSTITUTION.md`
- 规则层：`/Users/mac_claw/.openclaw/workspace/projects/jinclaw-governance/jinclaw-live-guardrails.md`
- 规则层：`/Users/mac_claw/.openclaw/workspace/tools/openmoss/control_center/doctor_coverage_contract.md`
- 流程层：`/Users/mac_claw/.openclaw/workspace/compat/gstack/prompts/jinclaw-gstack-lite.md`
- 流程层：`/Users/mac_claw/.openclaw/workspace/tools/openmoss/control_center/orchestrator.py`
- 流程层：`/Users/mac_claw/.openclaw/workspace/tools/openmoss/autonomy/task_contract.py`
- 流程层：`/Users/mac_claw/.openclaw/workspace/tools/openmoss/autonomy/preflight_engine.py`

版本化 source-of-truth 在：

- `/Users/mac_claw/.openclaw/workspace/projects/amazon-product-selection-engine/README.md`
- `/Users/mac_claw/.openclaw/workspace/projects/amazon-product-selection-engine/GOVERNANCE.md`
- `/Users/mac_claw/.openclaw/workspace/projects/amazon-product-selection-engine/config/project-config.json`
- `/Users/mac_claw/.openclaw/workspace/projects/amazon-product-selection-engine/config/stage-manifest.json`

本地运行态和业务产物继续只落在本机，不进 Git：

- `/Users/mac_claw/.openclaw/workspace/data/amazon-product-selection/`
- `/Users/mac_claw/.openclaw/workspace/output/amazon-product-selection`
- `/Users/mac_claw/.openclaw/workspace/projects/amazon-product-selection-engine/runtime/`
- `/Users/mac_claw/.openclaw/workspace/projects/amazon-product-selection-engine/reports/`

## 三、这次先做什么

本轮只执行第 1 阶段：

- 在已登录的 SellerSprite 账户里打开 `Product Research`
- 站点选择美国市场
- 月份选择最近 30 天
- 优先使用保存的 `中件FBM` 预设；如果页面没有显示该预设，则使用对应的规范化查询参数
- 点击 `Search Now`
- 点击 `Export`
- 点击 `My Exported Data`
- 下载官方导出的 `xlsx`
- 将导出文件保存到任务目录
- 验证文件可打开、可查看、可用于后续分析

## 四、任务框架

### 阶段 1：卖家精灵候选产品导出
输入：
- 浏览器登录态
- 卖家精灵筛选条件

输出：
- SellerSprite 官方导出 Excel
- 文件保存路径
- 文件可读性检查结果

产物位置：
- `/Users/mac_claw/.openclaw/workspace/data/amazon-product-selection/seller-sprite`

### 阶段 2：关键词提取
输入：
- 卖家精灵导出文件

输出：
- 标准化产品记录
- 每个产品的主要关键词

建议产物：
- `processed/candidate_products.*`
- `processed/product_keywords.*`

### 阶段 3：亚马逊关键词前台采集
输入：
- 关键词列表

输出：
- 关键词搜索结果数量
- 首页产品链接数量
- 首页产品链接的 review 区间
- 首页产品链接过去 30 天销量区间
- 首页产品链接最早/最晚上架时间

建议产物：
- `processed/amazon_keyword_searches.*`
- `processed/amazon_search_results.*`

### 阶段 4：关键词级分析整理
输入：
- 亚马逊搜索结果明细

输出：
- 每个关键词的统计结果
- 每个关键词带 1 个代表性产品 URL

建议产物：
- `processed/keyword_analysis.*`

### 阶段 5：最终表格输出
输入：
- 关键词分析结果

输出：
- 可直接查看和继续筛选的结果表格

产物位置：
- `/Users/mac_claw/.openclaw/workspace/output/amazon-product-selection`

## 五、阶段间接口约定

为了避免前面做完、后面接不上，先约定每一阶段最小接口：

- 阶段 1 向阶段 2 提供：原始导出文件路径、文件格式、表头信息
- 阶段 2 向阶段 3 提供：关键词清单、关键词来源产品
- 阶段 3 向阶段 4 提供：关键词搜索明细和首页商品明细
- 阶段 4 向阶段 5 提供：关键词级统计结果和代表 URL

## 六、第 1 阶段完成标准

只有同时满足下面几点，第 1 阶段才算完成：

1. 官方导出的 SellerSprite `xlsx` 已成功下载
2. 文件已保存到任务目录
3. 文件可以被打开查看
4. 能确认后续可以继续做字段识别和分析
5. 本地验证报告已生成

## 七、执行原则

- 先把链路跑通，再做自动化
- 先保留原始导出文件，不做破坏性修改
- 每个阶段都要留下可复查产物
- 下一阶段依赖的最小输入要在本阶段就记录清楚
- 版本化任务定义不放在被 `.gitignore` 忽略的目录里
