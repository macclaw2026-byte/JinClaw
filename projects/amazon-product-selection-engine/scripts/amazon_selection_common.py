#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List
from zipfile import ZipFile


SHEET_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

TRAILING_PHRASES = [
    "heavy duty",
    "upgraded",
    "portable",
    "foldable",
    "adjustable",
    "wider and thicker",
    "for seniors",
    "for women",
    "for men",
    "for mom",
    "for moms",
    "for kids",
]

TITLE_SPLITTERS = [
    " compatible with ",
    " works with ",
    " fits ",
    " with ",
    " for ",
]

NOISY_KEYWORD_TOKENS = {
    "compatible",
    "lightweight",
    "durable",
    "wear-resistant",
    "leak-proof",
    "sturdy",
    "indoor",
    "outdoor",
    "anti-slip",
    "folding",
    "included",
}

STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "for",
    "with",
    "to",
    "in",
    "on",
    "by",
    "from",
}


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.replace("\u2019", "'").replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_human_count(raw: str) -> int | None:
    text = normalize_text(raw).upper().replace(",", "").replace("+", "").strip()
    if not text or text in {"N/A", "--"}:
        return None
    multiplier = 1
    if text.endswith("K"):
        multiplier = 1000
        text = text[:-1]
    elif text.endswith("M"):
        multiplier = 1000000
        text = text[:-1]
    elif text.endswith("B"):
        multiplier = 1000000000
        text = text[:-1]
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return None


def safe_float(raw: str) -> float | None:
    text = normalize_text(raw).replace(",", "").strip()
    if not text or text in {"N/A", "--"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _column_index(column_ref: str) -> int:
    value = 0
    for char in column_ref:
        if not char.isalpha():
            break
        value = value * 26 + (ord(char.upper()) - ord("A") + 1)
    return value


def _read_xlsx_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    with ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
        workbook_sheets = workbook.find("a:sheets", SHEET_NS)
        sheets = list(workbook_sheets) if workbook_sheets is not None else []
        if not sheets:
            raise ValueError("xlsx workbook has no sheets")

        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in shared_root.findall("a:si", SHEET_NS):
                parts = [node.text or "" for node in item.iterfind(".//a:t", SHEET_NS)]
                shared_strings.append("".join(parts))

        first_sheet = sheets[0]
        rel_id = first_sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
        target = rel_map.get(rel_id)
        if not target:
            raise ValueError("xlsx workbook is missing the first sheet target")
        sheet_root = ET.fromstring(archive.read(f"xl/{target}"))

        rows: list[list[str]] = []
        for row in sheet_root.findall(".//a:sheetData/a:row", SHEET_NS):
            row_cells: Dict[int, str] = {}
            max_col = 0
            for cell in row.findall("a:c", SHEET_NS):
                ref = cell.attrib.get("r", "")
                col_index = _column_index("".join(ch for ch in ref if ch.isalpha())) if ref else max_col + 1
                cell_type = cell.attrib.get("t")
                value_node = cell.find("a:v", SHEET_NS)
                inline_node = cell.find("a:is", SHEET_NS)
                value = ""
                if cell_type == "s" and value_node is not None:
                    idx = int(value_node.text or "0")
                    value = shared_strings[idx] if idx < len(shared_strings) else ""
                elif cell_type == "inlineStr" and inline_node is not None:
                    value = "".join(node.text or "" for node in inline_node.iterfind(".//a:t", SHEET_NS))
                elif value_node is not None:
                    value = value_node.text or ""
                row_cells[col_index] = value
                max_col = max(max_col, col_index)
            rows.append([row_cells.get(index, "") for index in range(1, max_col + 1)])

    if not rows:
        raise ValueError("xlsx workbook has no rows")

    headers = rows[0]
    while headers and not normalize_text(headers[-1]):
        headers.pop()
    data_rows = []
    for row in rows[1:]:
        expanded = row[: len(headers)] + [""] * max(0, len(headers) - len(row))
        data_rows.append(expanded[: len(headers)])
    return headers, data_rows


def load_xlsx_records(path: Path) -> list[dict[str, str]]:
    headers, rows = _read_xlsx_rows(path)
    records: list[dict[str, str]] = []
    for row in rows:
        record = {headers[index]: row[index] if index < len(row) else "" for index in range(len(headers))}
        records.append(record)
    return records


def clean_keyword_phrase(text: str) -> str:
    value = normalize_text(text).lower()
    value = re.split(r"[,;|]", value, maxsplit=1)[0].strip()
    value = re.sub(r"\b(?:pack of|set of)\b.*$", "", value).strip()
    value = re.sub(r"\b[a-z]*\d+[a-z\d-]*\b", " ", value)
    value = value.replace("&", " ")
    value = re.sub(r"[^a-z0-9\s/-]", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" -,:;")
    changed = True
    while changed:
        changed = False
        for phrase in TRAILING_PHRASES:
            if value.endswith(phrase):
                value = value[: -len(phrase)].strip(" -,:;")
                changed = True
    return re.sub(r"\s+", " ", value).strip()


def _last_nonempty_line(text: str) -> str:
    lines = [normalize_text(line).strip() for line in str(text or "").splitlines()]
    lines = [line for line in lines if line]
    return lines[-1] if lines else ""


def _trim_title_candidate(text: str) -> str:
    value = normalize_text(text)
    value = re.split(r"[,;|]", value, maxsplit=1)[0].strip()
    for splitter in TITLE_SPLITTERS:
        lowered = value.lower()
        idx = lowered.find(splitter)
        if idx > 0:
            head = value[:idx].strip()
            if len(head.split()) >= 2:
                value = head
                break
    return clean_keyword_phrase(value)


def _keyword_score(candidate: str, *, subcategory_candidate: str = "") -> tuple[int, int]:
    value = clean_keyword_phrase(candidate)
    if not value:
        return (-999, 0)

    tokens = [token for token in value.split() if token and token not in STOPWORDS]
    word_count = len(tokens)
    score = 0

    if 2 <= word_count <= 5:
        score += 30
    elif word_count == 6:
        score += 15
    else:
        score -= abs(word_count - 4) * 8

    if re.search(r"[/'\"]", value):
        score -= 10
    if any(token in NOISY_KEYWORD_TOKENS for token in tokens):
        score -= 8
    if re.search(r"\b(?:inch|gallon|pack|set|kit|black|white|green|blue|gray|grey)\b", value):
        score -= 10
    if value == subcategory_candidate and subcategory_candidate:
        score += 6
    if len(value) > 55:
        score -= 12

    return (score, -len(value))


def _is_clean_title_keyword(candidate: str) -> bool:
    value = clean_keyword_phrase(candidate)
    tokens = [token for token in value.split() if token and token not in STOPWORDS]
    if not (2 <= len(tokens) <= 5):
        return False
    if re.search(r"[/'\"]", value):
        return False
    noisy_count = sum(1 for token in tokens if token in NOISY_KEYWORD_TOKENS)
    return noisy_count <= 1


def extract_primary_keyword(title: str, brand: str = "", subcategory: str = "", category_path: str = "") -> str:
    normalized_title = normalize_text(title)
    normalized_brand = normalize_text(brand)
    if normalized_brand and normalized_title.lower().startswith(normalized_brand.lower()):
        normalized_title = normalized_title[len(normalized_brand) :].lstrip(" -,:;")

    title_candidate = _trim_title_candidate(normalized_title)
    subcategory_candidate = clean_keyword_phrase(_last_nonempty_line(subcategory))
    category_candidate = clean_keyword_phrase(_last_nonempty_line(category_path.split(":")[-1] if category_path else ""))

    if _is_clean_title_keyword(title_candidate):
        return title_candidate

    candidates = [value for value in [title_candidate, subcategory_candidate, category_candidate] if value]
    if not candidates:
        return ""

    chosen = max(candidates, key=lambda item: _keyword_score(item, subcategory_candidate=subcategory_candidate))
    if len([token for token in chosen.split() if token not in STOPWORDS]) < 2:
        return subcategory_candidate or category_candidate or chosen
    return chosen


def build_alternate_keywords(title: str, subcategory: str = "", category_path: str = "") -> list[str]:
    candidates: List[str] = []
    for raw in [_trim_title_candidate(title), _last_nonempty_line(subcategory), category_path.split(":")[-1] if category_path else ""]:
        value = clean_keyword_phrase(raw)
        if not value or value in candidates:
            continue
        if len([token for token in value.split() if token not in STOPWORDS]) < 2:
            continue
        candidates.append(value)
    return candidates[:3]


def parse_amazon_result_count(text: str) -> int | None:
    patterns = [
        r"\d+-\d+ of over ([\d,]+) results",
        r"\d+-\d+ of ([\d,]+) results",
        r"over ([\d,]+) results",
    ]
    for pattern in patterns:
        found = re.search(pattern, text, flags=re.I)
        if found:
            return int(found.group(1).replace(",", ""))
    return None


def parse_launch_date(text: str) -> tuple[str, int | None]:
    found = re.search(r"Launch Date:([0-9]{4}-[0-9]{2}-[0-9]{2})\s*\(([\d,]+)days\)", text, flags=re.I)
    if not found:
        return "", None
    return found.group(1), int(found.group(2).replace(",", ""))


def parse_card_review_count(text: str) -> int | None:
    patterns = [
        r"Rating:\s*[\r\n ]*[\d.]+\(([\d,\.KM]+)\)",
        r"out of 5 stars\s*\(([\d,\.KM]+)\)",
        r"\(([\d,\.KM]+)\)",
    ]
    for pattern in patterns:
        found = re.search(pattern, text, flags=re.I)
        if found:
            value = parse_human_count(found.group(1))
            if value is not None:
                return value
    return None


def parse_card_rating(text: str) -> float | None:
    patterns = [
        r"Rating:\s*[\r\n ]*([\d.]+)\(",
        r"([\d.]+)\s*out of 5 stars",
    ]
    for pattern in patterns:
        found = re.search(pattern, text, flags=re.I)
        if found:
            try:
                return float(found.group(1))
            except ValueError:
                continue
    return None


def parse_card_sales_30d(text: str) -> int | None:
    patterns = [
        r"Variation Sold\(30 days\):\s*([0-9.,KMB+]+)",
        r"([0-9.,KMB+]+)\s*bought in past month",
    ]
    for pattern in patterns:
        found = re.search(pattern, text, flags=re.I)
        if found:
            value = parse_human_count(found.group(1))
            if value is not None:
                return value
    return None
