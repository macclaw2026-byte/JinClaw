#!/usr/bin/env python3
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

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / 'config' / 'data_sources.json'

with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    cfg = json.load(f)

con = duckdb.connect(cfg['database_path'], read_only=True)

queries = {
    'total_rows': 'SELECT COUNT(*) FROM businesses',
    'rows_with_email': 'SELECT COUNT(*) FROM businesses WHERE has_email',
    'rows_with_website': 'SELECT COUNT(*) FROM businesses WHERE has_website',
    'top_cities': '''
        SELECT city, COUNT(*) AS n
        FROM businesses
        GROUP BY 1
        ORDER BY n DESC
        LIMIT 15
    ''',
    'top_industries': '''
        SELECT industry, COUNT(*) AS n
        FROM businesses
        WHERE industry IS NOT NULL AND industry <> ''
        GROUP BY 1
        ORDER BY n DESC
        LIMIT 15
    ''',
}

for name, sql in queries.items():
    print(f'\n## {name}')
    print(con.execute(sql).fetchdf().to_string(index=False))
