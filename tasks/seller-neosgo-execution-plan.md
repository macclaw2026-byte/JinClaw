# NeosGo 潜客引擎执行方案（Plan Stage）

更新时间：2026-03-25 17:00 PDT

## 一、当前已验证事实

### 1) 当前已经存在的可用数据底座
- 当前项目内已经有一个可读的 DuckDB 工作库：
  - `/Users/mac_claw/.openclaw/workspace/projects/ma-data-workbench/data/db/ma_data.duckdb`
- 这个库当前已验证可正常读取。
- 当前已验证数据规模：`2,987,364` 行。

### 2) 项目外、本机内的数据源
已确认在本机 Downloads 下存在大量项目外数据包/原始数据：
- `MA_Business_Email_Data/MA_B2B_23_1.csv`
- `MA_Business_Email_Data/MA_B2B_23_2.csv`
- `US_Business_Email_Data_07/NY_B2B_23_1.csv`
- 以及多个州级压缩包：
  - `US_Business_Email_Data_01.zip`
  - `US_Business_Email_Data_02.zip`
  - `US_Business_Email_Data_03.zip`
  - `US_Business_Email_Data_04.zip`
  - `US_Business_Email_Data_05.zip`
  - `US_Business_Email_Data_06.zip`
  - `US_Business_Email_Data_07.zip`
  - `US_Business_Email_Data_08.zip`
  - `NY_Business_Email_Data.zip`
  - `MA_Business_Email_Data.zip`

### 3) 潜客主类目与你的业务逻辑
需要作为第一优先级建模的潜客群体：
- 室内设计师
- 建筑商 / builder
- 房屋中介 / realtor / broker
- contractor
- 电工 / electrician

业务核心：
- NeosGo professional 账号可返佣
- 所以筛客不是泛流量筛选，而是要做 **professional rebate-fit lead scoring**
- 即：谁最可能成为“带项目、带客户、可持续转介绍/返佣”的职业型合作客户

---

## 二、数据库 access 方案对比

这里不假设“唯一真数据库”已经完全找到，而是面向本机真实情况设计可落地路径。

### 方案 A：直接把项目外原始 CSV 当主查询源
**做法**
- 每次筛选时直接读取 Downloads 里的 CSV / 解压后的 CSV
- UI / CLI 直接查询原始文件

**优点**
- 实现最简单
- 不需要额外同步层

**缺点**
- 对百万级数据不稳
- 多文件跨州查询会变慢
- 每次查询重复解析 CSV，成本高
- 后续做复杂打分、画像、导出、迭代优化都不适合

**结论**
- 不选为主方案
- 只可作为“原始接入层 / 首次导入层”存在

---

### 方案 B：找到项目外 canonical 数据库后，直接附加查询
**做法**
- 如果本机存在真正的外部 sqlite / duckdb / db 文件
- 使用 DuckDB 进行 attach / 外部扫描
- 例如：
  - 外部 DuckDB：直接 `ATTACH`
  - 外部 SQLite：DuckDB sqlite extension 读写接入

**优点**
- 不复制全部数据即可先访问
- 能保持与原数据库相对接近
- 适合做探查、核验、抽样分析

**缺点**
- 如果原库结构混乱、字段不统一、更新不可控，后续业务层会很脆
- 直接在源库上做重逻辑查询，长期性能与可维护性不稳定
- 不利于做标准化标签、画像、打分版本化

**结论**
- 适合做“发现源库 + 验证接入”的中间方案
- 不适合作为最终长期业务分析层

---

### 方案 C：外部数据接入 + 本地 DuckDB/Parquet 统一分析层（推荐）
**做法**
1. 把项目外的 CSV / zip / 外部 DB 识别为 **source-of-truth 输入层**
2. 在项目内维护一个 **标准化 DuckDB + Parquet 分析层**
3. 所有 UI、筛选、打分、导出、后续自动化都走这个统一层
4. 对外部数据做：
   - 增量导入
   - 标准化清洗
   - 去重
   - 标签化
   - 打分物化

**优点**
- 最适合百万级本地数据
- DuckDB + Parquet 对分析型多条件过滤很合适
- 方便做版本化评分和回溯
- 方便后续扩展成“多州、多职业、持续导入、持续优化”
- 适合后续导出名单、营销节奏、反馈闭环

**缺点**
- 前期工程设计稍重
- 需要把接入层、标准层、业务层分清楚

**结论**
- 这是最佳主方案
- 也是后续自动化、迭代优化、长期运营最稳的路径

---

## 三、选定方案

### 最终选定：方案 C
即：
**“项目外原始数据 / 外部数据库 → 接入层 → DuckDB + Parquet 统一分析层 → 潜客评分与名单输出层”**

### 原因
1. 你明确说数据量是百万级，说明数据库层必须首先为规模负责。
2. 你后续不仅要筛客，还要做：
   - 画像
   - 打分
   - 营销策略
   - 客户开发方案
   - 自动持续迭代
3. 这些都要求底层数据结构稳定、可重复、可追溯，而不是零散直接查原文件。

---

## 四、推荐数据库架构

## 1. 输入层（outside project）
职责：保存原始真实来源
- Downloads 下 zip / csv
- 未来如发现真正外部 sqlite/duckdb/db，也归这里

原则：
- 不直接在输入层上堆业务逻辑
- 保留原始文件，便于重建

## 2. 标准化层（inside project, analytics layer）
建议保留/扩展：
- `raw_file_registry`：记录每个源文件、时间、州、哈希、导入批次
- `staging_businesses`：原始字段标准化后的中间表
- `businesses`：主实体表
- `contacts`：联系人粒度表（如果同企业多人）
- `domains`：网站/域名粒度表
- `lead_candidates`：潜客候选表
- `lead_scores`：打分结果表（支持版本）
- `lead_segments`：职业标签与细分标签表

## 3. 业务输出层
- `v_professional_leads`
- `v_neosgo_priority_leads`
- `v_rebate_fit_leads`
- `v_outreach_ready_leads`

作用：
- 给 UI / CLI / 导出直接使用
- 避免每次把复杂打分 SQL 临时拼起来

---

## 五、潜客评分系统设计（清晰、详细、可解释）

不能只做一个总分，必须拆成多维度。

### 总体结构
建议总分 100 分，由 6 个一级维度组成：

1. **职业匹配分（0-25）**
2. **行业/场景匹配分（0-20）**
3. **商业价值分（0-15）**
4. **触达质量分（0-15）**
5. **项目转化潜力分（0-15）**
6. **Professional返佣适配分（0-10）**

---

### 1) 职业匹配分（0-25）
这是第一优先级。

#### 建议分档
- 室内设计师 / interior designer：25
- builder / 建筑商 / home builder：24
- realtor / broker / 房屋中介：22
- contractor / general contractor：21
- electrician：19
- 其它弱相关职业：0-12

#### 判定来源
综合以下字段：
- `title`
- `industry`
- `company_name`
- `sic_code`（如果可映射）
- 网站文本（后续可选增强）

#### 要求
- 不是简单 keyword like，而是：
  - 主标签（primary_profession）
  - 次标签（secondary_profession）
  - 置信度（confidence）

---

### 2) 行业/场景匹配分（0-20）
衡量是否真的和 NeosGo 产品购买场景强相关。

#### 高分特征
- 室内设计 / 装修 / home improvement
- 新房建造 / remodeling / renovation
- real estate staging / listing prep
- lighting / fixtures / electrical / home decor
- 商业空间/住宅空间方案输出者

#### 低分特征
- 与家装/建材/空间改造无直接关系
- 虽是专业人士，但不掌握采购建议权

---

### 3) 商业价值分（0-15）
衡量客户价值规模。

参考字段：
- `employee_count`
- `annual_sales`
- 公司规模标签
- 是否多地点/多分支

逻辑：
- 太小：可能单体项目少
- 太大：可能采购链路复杂、转化慢
- 中小到中型专业机构通常更优先

可做“最优区间”而非越大越高。

---

### 4) 触达质量分（0-15）
营销能不能落地，关键看是否能联系上。

参考项：
- 有邮箱
- 有官网
- 联系人姓名完整
- 直线电话存在
- 域名质量高

建议：
- 邮箱 + 官网 + 联系人姓名齐全 = 高分
- 只有公司电话、无官网/无邮箱 = 低分

---

### 5) 项目转化潜力分（0-15）
判断其是否更可能持续带来项目。

高分画像：
- 经常服务终端客户
- 会向客户推荐产品/材料
- 在装修/建造/成交场景中有建议权
- 具备转介绍/返佣闭环的合理性

举例：
- 室内设计师：高
- builder：高
- realtor：中高（尤其 staging / listing prep）
- electrician：中高（更偏安装与指定采购）
- 普通行政岗位：低

---

### 6) Professional返佣适配分（0-10）
这是 NeosGo 特有逻辑，必须单列。

核心判断：
- 是否天然适合 professional 账号机制
- 是否可能通过返佣推动长期合作
- 是否属于“有客户决策影响力”的职业中介层

高分：
- interior designer
- builder / contractor
- realtor / broker（有 staging / remodel / furnishing 关联时）
- electrician（带采购建议或安装配套时）

---

## 六、输出等级建议

按总分把线索分层：
- **A+（85-100）**：立即开发，优先人工策略 + 深度跟进
- **A（75-84）**：优先开发
- **B（60-74）**：自动化培育 + 次优先人工触达
- **C（40-59）**：保留，后续再筛
- **D（<40）**：暂不开发

同时保留“命中原因”字段：
- `score_reason_primary`
- `score_reason_detail`
- `matched_profession_signals`
- `missing_contact_penalties`

这样后续每一条线索都可解释，不会变成黑箱分数。

---

## 七、计划阶段最终建议

### 推荐主路径
1. **继续定位项目外 canonical 数据源/数据库**
2. **把所有项目外数据纳入统一接入清单**
3. **维持 DuckDB + Parquet 作为分析主层**
4. **先做职业标签系统，再做可解释评分系统**
5. **长消息统一输出到 md 文件**

### 接下来最合理的执行顺序
1. 扫描并登记 Downloads 里所有州数据包 / CSV
2. 识别是否还有真正的外部数据库文件（sqlite/duckdb/db）
3. 设计统一导入规范和批次表
4. 扩展 schema：segments / scores / lead views
5. 实现第一版职业识别 + 评分逻辑
6. 在 UI / CLI 输出 A/A+/B 层名单

---

## 八、当前阶段选择结论

**已选择执行路径：方案 C（外部数据接入 + 本地 DuckDB/Parquet 统一分析层）**

这条路径：
- 不突破本地安全边界
- 对百万级数据稳定
- 能兼容未来发现的项目外 canonical 数据库
- 最适合承载 NeosGo professional 返佣型潜客系统
