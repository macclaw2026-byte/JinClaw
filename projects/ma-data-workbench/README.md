# MA Data Workbench

本地大体量商业数据筛选与导出项目。

## 目标

- 导入 MA 原始 CSV 数据
- 用低内存方式查询 / 筛选 / 导出
- 为后续数据整理、分析、名单生成提供稳定底座
- 让 MacClaw 可以直接代你操作

## 技术选择

- **DuckDB**：本地分析型数据库，适合大 CSV / Parquet，资源占用低
- **Parquet**：列式存储，加快查询和导出
- **Streamlit**：本地轻量界面，快速筛选和下载结果
- **Python CLI**：方便我直接批量操作、查询、导出和分析

## 项目结构

```text
ma-data-workbench/
  app.py                     # 本地筛选界面
  requirements.txt
  .venv/                     # Python 虚拟环境
  config/
    data_sources.json        # 原始数据路径配置
  data/
    raw/                     # 原始文件软链接/占位
    db/                      # duckdb 数据库
    parquet/                 # parquet 数据
    exports/                 # 导出结果
    cache/                   # 中间缓存
  scripts/
    ingest_ma_data.py        # 导入与预处理
    query_export.py          # CLI 查询导出
    profile_data.py          # 数据概览
  sql/
    views.sql                # 视图定义
```

## 当前原始数据

默认读取：

- `/Users/mac_claw/Downloads/MA_Business_Email_Data/MA_B2B_23_1.csv`
- `/Users/mac_claw/Downloads/MA_Business_Email_Data/MA_B2B_23_2.csv`

## 启动

### 1. 激活环境

```bash
cd /Users/mac_claw/.openclaw/workspace/projects/ma-data-workbench
source .venv/bin/activate
```

### 2. 导入数据

```bash
python scripts/ingest_ma_data.py
```

### 3. 查看数据概览

```bash
python scripts/profile_data.py
```

### 4. 启动界面

```bash
streamlit run app.py
```

### 5. CLI 导出示例

```bash
python scripts/query_export.py \
  --city Boston \
  --has-email yes \
  --industry-keyword dental \
  --limit 5000 \
  --format csv
```

## 设计原则

- 不把全量 CSV 反复读进内存
- 先转 Parquet，再基于 DuckDB 查询
- 所有列表默认分页
- 导出单独生成文件，避免界面卡顿
- 为后续名单整理 / 数据分析 / 联系动作做准备

## 关于发邮件

这个项目目前只负责：

- 结构化筛选
- 清单生成
- 导出联系人结果
- 为后续邮件动作准备数据

真正对外发送邮件属于外部动作，执行前仍应明确确认。
