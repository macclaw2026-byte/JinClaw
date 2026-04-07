# Neosgo lead engine followup-4 understand 阶段检查点

日期：2026-03-30
任务来源：background runtime execution request / task_id `neosgo-lead-engine-followup-4`
阶段：understand

## 1. 目标重述

本轮任务目标：
1. 先修复当前有问题的抓取工具
2. 然后测试抓取 Amazon、Walmart、Temu、1688 四个站点的数据能力
3. 根据测试结果做评测排序并给出报告

完成口径：
- 目标被验证
- 阻塞被识别并尽量消解
- 不突破本地安全边界
- 输出最终检查点/报告材料

## 2. 已确认的本地上下文

### 2.1 已存在、可复用的抓取能力
- 本地 Crawl4AI 包装器存在：`tools/bin/crawl4ai`
- 包装器实际指向本地 venv：`tools/crawl4ai-venv`
- Amazon 已有在用抽取脚本：`skills/product-selection-engine/scripts/extract_amazon_public_candidates.py`
- Amazon 已有持续维护环：`tools/bin/amazon_premium_wholesale_maintenance_loop.sh`

### 2.2 已存在的历史结论
- Amazon 公共搜索抽取已经被接入并持续运行，但仍有“间歇性抽取不稳定”备注，不是完全无问题状态。
- Temu/1688 方向此前已确认核心约束：
  - 1688 搜索/详情存在登录门槛或公开可读性差
  - Temu 类目/商品访问可能触发安全验证
- Walmart 此前在本地资料里未见成熟抓取流水线，属于本轮需要新增验证的站点。

## 3. 本轮直接复现结果

使用本地 `tools/bin/crawl4ai` 对四站做最低可达性测试：
- Amazon: `https://www.amazon.com/s?k=drawer+organizer`
- Walmart: `https://www.walmart.com/search?q=drawer+organizer`
- Temu: `https://www.temu.com/`
- 1688: `https://www.1688.com/`

### 3.1 结果摘要

#### Amazon
- 返回码：0
- stdout 长度：505238
- 结果：成功拿到大量 markdown 内容，包含搜索结果结构与商品链接线索
- 结论：当前四站中，Amazon 是唯一已被直接验证为“本地 crawl4ai + 公共页面”可稳定产出较丰富结果的站点

#### Walmart
- 返回码：0
- stdout 长度：511
- 结果：页面主体为 `Robot or human?` 人机校验提示
- 结论：当前公开抓取主路径被机器人验证页拦截，不能视为可用抓取结果

#### Temu
- 返回码：0
- stdout 长度：6673
- 结果：首页可读，能拿到一定公开内容
- 结论：Temu 首页级公开可达性成立，但这不等于搜索页/类目页/商品页稳定可抓；此前历史结论提示更深层页面仍可能触发安全验证

#### 1688
- 返回码：0
- stdout 长度：2
- 结果：几乎空输出
- 结论：当前本地 crawl4ai 对 1688 首页公开抓取基本无有效结果，处于不可用状态

### 3.2 额外技术观察
- 每次 crawl4ai 调用 stderr 都出现 `RequestsDependencyWarning`
- 该 warning 当前未阻断执行，但属于环境健康度瑕疵，后续若修复工具稳定性，值得一并清理

## 4. 对“有问题的抓取工具”的理解更新

根据本地证据，本轮真正的问题不只是“某个脚本报错”，而是三层问题叠加：

### 4.1 工具层
- crawl4ai 本身能跑通，但环境存在依赖 warning
- 对不同站点的适配能力差异很大，没有统一的站点级健康检查/结果判定器

### 4.2 站点层
- Amazon：可抓，但抽取质量存在波动
- Walmart：当前主路径命中机器人校验页
- Temu：首页可读，但详情/类目稳定性仍存疑
- 1688：当前几乎无有效公开输出

### 4.3 工作流层
- 目前本地只有 Amazon 有“抽取脚本 + 维护环 + 质量门”组合
- Walmart / Temu / 1688 缺少统一测试器、统一质量判定、统一报告产出
- 因此用户要的“四站评测排序报告”目前没有现成流水线，需先补一层通用测试与证据化框架

## 5. 当前安全边界判断

必须继续遵守：
- 不绕过登录门槛
- 不绕过验证码/机器人校验/拼图
- 不引入高风险第三方黑盒抓取器
- 仅在公开、合理、可审计路径下修复和测试

因此本轮“修复抓取工具”的允许方向应是：
- 修复本地工具环境问题
- 增加站点级测试器与结果分类
- 调整公开可访问页的抓取策略
- 输出基于公开证据的评测报告

不允许方向：
- 代理/反检测/验证码绕过
- 登录态抓取
- 不可审计的外部 SaaS 抓取替代

## 6. 本阶段已完成的本地修复/重建

虽然还没有把 Walmart / Temu / 1688 都修到“可稳定抓取”，但已经完成一个重要的工具层修复：

- 新建了统一四站 smoke test 脚本：`tools/site_smoke_test.py`
- 该脚本会对 Amazon / Walmart / Temu / 1688 做一致化测试，并落盘：
  - 返回码
  - stdout/stderr 长度
  - 命中机器人校验/空白输出/可读页面的分类
  - warning 标记
  - 排序结果
- 已生成首个统一测试结果文件：
  - `reports/site-smoke-tests/site-smoke-test-20260330-060603.json`

这一步的意义是：
- 把“零散人工观察”修成了“可复跑、可比较、可排序”的本地测试能力
- 为后续真正修 crawl4ai 依赖、站点策略和最终报告打下统一证据基础

## 7. understand 阶段结论

### 6.1 当前最可能的可执行主线
按当前证据，最合理的执行顺序应为：
1. 先给本地 crawl4ai 建一个四站统一 smoke test / 结果分类器
2. 先修“工具级问题”（至少包括 warning 可见性、结果判定、输出落盘）
3. 再对四站分别做公开页面测试
4. 基于可用性、字段丰富度、稳定性、阻塞强度做排序
5. 生成报告

### 6.2 当前初步站点排序（仅基于 understand 阶段证据）
1. Amazon — 已验证最可用
2. Temu — 首页级可达，但深层稳定性未证实
3. Walmart — 可访问但直接遇到机器人校验页
4. 1688 — 当前几乎无有效输出

注意：以上只是 understand 阶段的暂定排序，不是最终测试报告排序；后续 execute 阶段应在统一测试脚本下复核。

## 7. 下一具体动作

进入 execute 阶段时，优先动作应是：
1. 新建一个本地四站统一抓取 smoke test 脚本
2. 统一记录：返回码、输出长度、命中校验/空白/可读结构、关键字段覆盖
3. 如果能低风险修复，则先修本地 crawl4ai 环境 warning 与测试输出结构
4. 用统一结果生成最终四站评测排序报告
