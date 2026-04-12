# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
import json
from pathlib import Path
import duckdb
import streamlit as st

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / 'config' / 'data_sources.json'

st.set_page_config(page_title='MA Data Workbench', layout='wide')
st.title('MA Data Workbench')
st.caption('低内存本地筛选 / 导出 / 分析入口')

with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    cfg = json.load(f)

DB_PATH = cfg['database_path']


@st.cache_resource
def get_conn():
    return duckdb.connect(DB_PATH, read_only=True)


conn = get_conn()
state_options = ['ALL'] + [
    row[0]
    for row in conn.execute(
        "SELECT DISTINCT state FROM businesses WHERE state IS NOT NULL AND state <> '' ORDER BY state"
    ).fetchall()
]

with st.sidebar:
    st.header('筛选条件')
    selected_state = st.selectbox('State', state_options, index=0)
    city = st.text_input('City contains')
    county = st.text_input('County contains')
    company_keyword = st.text_input('Company keyword')
    industry_keyword = st.text_input('Industry keyword')
    title_keyword = st.text_input('Title keyword')
    has_email = st.selectbox('Has email', ['any', 'yes', 'no'])
    has_website = st.selectbox('Has website', ['any', 'yes', 'no'])
    min_employees_enabled = st.checkbox('Set min employees')
    min_employees = st.number_input('Min employees', min_value=0, value=0) if min_employees_enabled else None
    max_employees_enabled = st.checkbox('Set max employees')
    max_employees = st.number_input('Max employees', min_value=0, value=1000) if max_employees_enabled else None
    limit = st.slider('Rows per page', min_value=50, max_value=5000, value=200, step=50)


def build_filters():
    where = []
    params = []
    if selected_state != 'ALL':
        where.append('state = ?')
        params.append(selected_state)
    if city:
        where.append('city ILIKE ?')
        params.append(f'%{city}%')
    if county:
        where.append('county ILIKE ?')
        params.append(f'%{county}%')
    if company_keyword:
        where.append('company_name ILIKE ?')
        params.append(f'%{company_keyword}%')
    if industry_keyword:
        where.append('industry ILIKE ?')
        params.append(f'%{industry_keyword}%')
    if title_keyword:
        where.append('title ILIKE ?')
        params.append(f'%{title_keyword}%')
    if has_email != 'any':
        where.append('has_email = ?')
        params.append(has_email == 'yes')
    if has_website != 'any':
        where.append('has_website = ?')
        params.append(has_website == 'yes')
    if min_employees is not None:
        where.append('employee_count >= ?')
        params.append(int(min_employees))
    if max_employees is not None:
        where.append('employee_count <= ?')
        params.append(int(max_employees))
    clause = (' WHERE ' + ' AND '.join(where)) if where else ''
    return clause, params


stats_clause, stats_params = build_filters()
stats = conn.execute(
    'SELECT COUNT(*) AS total_rows, '
    'SUM(CASE WHEN has_email THEN 1 ELSE 0 END) AS rows_with_email, '
    'SUM(CASE WHEN has_website THEN 1 ELSE 0 END) AS rows_with_website '
    'FROM businesses' + stats_clause,
    stats_params,
).fetchone()

c1, c2, c3 = st.columns(3)
c1.metric('总行数', f'{stats[0]:,}')
c2.metric('有邮箱', f'{stats[1] or 0:,}')
c3.metric('有网站', f'{stats[2] or 0:,}')

clause, params = build_filters()
base_from = ' FROM v_businesses'
count_sql = 'SELECT COUNT(*)' + base_from + clause

page = st.number_input('Page', min_value=1, value=1, step=1)
offset = (page - 1) * limit
paged_sql = 'SELECT *' + base_from + clause + f' ORDER BY company_name NULLS LAST LIMIT {limit} OFFSET {offset}'

match_count = conn.execute(count_sql, params).fetchone()[0]
st.subheader(f'匹配结果：{match_count:,}')

df = conn.execute(paged_sql, params).fetchdf()
st.dataframe(df, width='stretch', hide_index=True)

csv_sql = 'SELECT *' + base_from + clause + ' ORDER BY company_name NULLS LAST LIMIT 50000'
csv_data = conn.execute(csv_sql, params).fetchdf().to_csv(index=False).encode('utf-8-sig')
filename_state = selected_state.lower() if selected_state != 'ALL' else 'all_states'
st.download_button('下载 CSV（最多 50,000 行）', data=csv_data, file_name=f'{filename_state}_filtered_results.csv', mime='text/csv')

st.subheader('快速分析')
col1, col2 = st.columns(2)
with col1:
    top_cities_sql = 'SELECT city, COUNT(*) AS n' + base_from + clause + ' GROUP BY city ORDER BY n DESC LIMIT 15'
    top_cities = conn.execute(top_cities_sql, params).fetchdf()
    st.write('Top cities')
    st.dataframe(top_cities, width='stretch', hide_index=True)
with col2:
    industry_clause = clause
    if industry_clause:
        industry_clause += " AND industry IS NOT NULL AND industry <> ''"
    else:
        industry_clause = " WHERE industry IS NOT NULL AND industry <> ''"
    top_industries_sql = 'SELECT industry, COUNT(*) AS n' + base_from + industry_clause + ' GROUP BY industry ORDER BY n DESC LIMIT 15'
    top_industries = conn.execute(top_industries_sql, params).fetchdf()
    st.write('Top industries')
    st.dataframe(top_industries, width='stretch', hide_index=True)
