# Neosgo 潜客筛选逻辑与画像

## 总体方法
采用“双层筛选”：
1. 规则过滤（保证基础质量）
2. 可解释打分（保证优先级）

## 第一层：规则过滤
保留对象必须尽量满足：
- 有有效邮箱
- 有网站
- 主体信息完整（公司名/城市/州基本齐全）
- 能归到目标行业或相邻行业
- 不属于重复主体

## 第二层：可解释打分
总分 100，由六部分组成：

### 1. 行业匹配度（0-30）
优先人群：
- designer
- architect
- builder
- contractor
- electrician
- lighting
- furniture_retailer
- kitchen_bath
- property_manager
- hospitality
- realtor

### 2. 决策影响力（0-20）
优先 title：
- owner / founder / principal / president / partner
- director / manager / procurement / purchasing
- designer / architect / realtor / project manager

### 3. 企业规模（0-15）
优先：
- core_smb（通常最容易成交且流程较短）
- micro（可快速成交）
- large（单体价值高但周期长）

### 4. Neosgo 适配度（0-20）
分为：
- trade_buyer
- channel_buyer
- influencer

### 5. 可触达性（0-10）
由邮箱、电话、网站、是否有明确联系人组成。

### 6. 市场优先级（0-5）
当前优先州：
- CA
- TX
- FL
- NY
- NJ
- IL
- WA
- GA
- NC
- VA
- MA

## 潜客画像

### Persona A：设计/建筑事务所
- 决策角色强
- 审美与选品影响力大
- 适合 trade account、样品、项目报价

### Persona B：Builder / Contractor
- 项目采购更稳定
- 看重供货、价格、效率
- 适合项目单、批量单、持续补货

### Persona C：Electrician / Lighting installer
- 对灯具和安装链路有影响力
- 适合推荐合作和项目配套

### Persona D：Furniture retailer / showroom / kitchen & bath
- 偏渠道合作
- 适合批发、样品、陈列合作

### Persona E：Property / Hospitality / Realtor
- 更偏项目、翻新、样板房、推荐链条
- 需要更谨慎地判断成交路径

## 当前模型的已知缺口
- `other` 占比仍然高，说明行业归类还不够细
- `decision_role_level=unclear` 占比偏高，说明 title 词典仍需扩充
- 后续应加入真实反馈驱动的权重修正
