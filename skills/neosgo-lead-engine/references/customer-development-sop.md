# Neosgo 客户开发 SOP

## 目标
把高分潜客从“名单”推进到“网站成交或线下成交”。

## 流程总览
1. 数据入库
2. 清洗/去重
3. 评分/分群
4. 生成外联队列
5. 首次触达
6. 跟进
7. 识别高意向
8. 推动报价 / 索样 / 沟通
9. 成交或归档
10. 回写结果并优化模型

## 状态流转
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

## 执行动作

### A. 每日批处理
1. 检查新压缩包/CSV
2. 增量导入数据库
3. 重建 normalized / deduped / scored 层
4. 生成新增 S/A 潜客
5. 刷新 outreach_queue
6. 生成日报

### B. 触达前检查
1. 是否有有效邮箱
2. 是否有网站
3. 是否属于目标行业/角色
4. 是否已在 do_not_contact
5. 是否最近已触达

### C. 首次触达
- 根据 segment_primary 选择 campaign variant
- 优先联系 S/A 级潜客
- 先从小批量开始，优先高分州与高分角色

### D. 跟进逻辑
- 无回复：按 Day 3 / 7 / 12 节奏跟进
- 有回复：转 qualified
- 明确项目需求：转 quote_requested
- 需要样品：转 sample_requested
- 愿意沟通：转 meeting_booked
- 已成交：转 won
- 明确拒绝：转 lost / do_not_contact

### E. 网站或线下成交路径
**网站成交**
- 引导至 trade account 申请页 / quote request 页 / catalog 页

**线下成交**
- 先收集项目需求
- 再报价 / 样品 / 目录支持
- 最后推进电话会 / 视频会 / 拜访

## 数据回写要求
每次有效动作至少记录：
- queue_id
- file_id
- event_type
- event_time
- payload_json

## 每周复盘
- 哪些 segment 回复最好
- 哪些职位转化最高
- 哪些州最值得优先开发
- 哪些文案要停掉或放大
- 哪些 leads 应加入排除名单
