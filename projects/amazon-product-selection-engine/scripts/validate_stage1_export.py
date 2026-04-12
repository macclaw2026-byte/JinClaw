#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
import argparse
import csv
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile


REQUIRED_HEADERS = [
    "Product Title",
    "ASIN",
    "Category",
    "Price",
    "Review Count",
    "Rating",
    "Monthly Sales",
    "Launch Date",
]

XLSX_HEADER_ALIASES = {
    "Product Title": ["Product Title"],
    "ASIN": ["ASIN"],
    "Category": ["Category"],
    "Price": ["Price($)", "Price"],
    "Review Count": ["Ratings", "Review Count"],
    "Rating": ["Rating"],
    "Monthly Sales": ["Sales", "Monthly Sales"],
    "Launch Date": ["Date Available", "Launch Date"],
}

SHEET_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_csv(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"export file not found: {path}")
    if path.stat().st_size <= 0:
        raise ValueError(f"export file is empty: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        missing = [header for header in REQUIRED_HEADERS if header not in headers]
        rows = list(reader)

    if missing:
        raise ValueError(f"missing required headers: {missing}")
    if not rows:
        raise ValueError("export file has no data rows")

    first_row = rows[0]
    return {
        "file_path": str(path),
        "file_name": path.name,
        "file_format": path.suffix.lower().lstrip("."),
        "file_size_bytes": path.stat().st_size,
        "headers": headers,
        "header_preview": headers[:8],
        "row_count_estimate": len(rows),
        "sample_asin": first_row.get("ASIN"),
        "sample_title": first_row.get("Product Title"),
        "validated_at": utc_now(),
        "status": "ok",
    }


def _load_xlsx_rows(path: Path) -> tuple[list[str], list[list[str]], list[str]]:
    with ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}

        sheets = []
        workbook_sheets = workbook.find("a:sheets", SHEET_NS)
        for sheet in list(workbook_sheets) if workbook_sheets is not None else []:
            sheets.append(
                {
                    "name": sheet.attrib.get("name", ""),
                    "rid": sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", ""),
                }
            )
        if not sheets:
            raise ValueError("xlsx workbook has no sheets")

        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in shared_root.findall("a:si", SHEET_NS):
                parts = [node.text or "" for node in item.iterfind(".//a:t", SHEET_NS)]
                shared_strings.append("".join(parts))

        first_sheet = sheets[0]
        target = rel_map.get(first_sheet["rid"])
        if not target:
            raise ValueError("xlsx workbook is missing the first sheet target")
        sheet_root = ET.fromstring(archive.read(f"xl/{target}"))

        rows: list[list[str]] = []
        for row in sheet_root.findall(".//a:sheetData/a:row", SHEET_NS):
            values: list[str] = []
            for cell in row.findall("a:c", SHEET_NS):
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
                values.append(value)
            rows.append(values)

    if not rows:
        raise ValueError("xlsx workbook has no rows")
    headers = rows[0]
    data_rows = rows[1:]
    return headers, data_rows, [sheet["name"] for sheet in sheets]


def validate_xlsx(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"export file not found: {path}")
    if path.stat().st_size <= 0:
        raise ValueError(f"export file is empty: {path}")

    headers, rows, sheet_names = _load_xlsx_rows(path)
    missing = []
    resolved_headers: dict[str, str] = {}
    for canonical, aliases in XLSX_HEADER_ALIASES.items():
        matched = next((alias for alias in aliases if alias in headers), None)
        if not matched:
            missing.append(canonical)
            continue
        resolved_headers[canonical] = matched

    if missing:
        raise ValueError(f"missing required headers: {missing}")
    if not rows:
        raise ValueError("export file has no data rows")

    first_row = rows[0]
    row_map = {headers[idx]: first_row[idx] if idx < len(first_row) else "" for idx in range(len(headers))}
    return {
        "file_path": str(path),
        "file_name": path.name,
        "file_format": path.suffix.lower().lstrip("."),
        "file_size_bytes": path.stat().st_size,
        "sheet_names": sheet_names,
        "headers": headers,
        "header_preview": headers[:8],
        "row_count_estimate": len(rows),
        "sample_asin": row_map.get(resolved_headers["ASIN"], ""),
        "sample_title": row_map.get(resolved_headers["Product Title"], ""),
        "validated_at": utc_now(),
        "status": "ok",
    }


def validate_export(path: Path) -> dict:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return validate_csv(path)
    if suffix == ".xlsx":
        return validate_xlsx(path)
    raise ValueError(f"unsupported export format: {suffix or 'no suffix'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate stage 1 SellerSprite export for the Amazon product-selection task.")
    parser.add_argument("--input", required=True, help="Path to the exported SellerSprite file (.csv or .xlsx).")
    parser.add_argument("--report", required=True, help="Path to write the JSON validation report.")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    report_path = Path(args.report).expanduser().resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        report = validate_export(input_path)
    except Exception as exc:  # noqa: BLE001
        report = {
            "file_path": str(input_path),
            "validated_at": utc_now(),
            "status": "error",
            "error": str(exc),
        }
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=True))
        return 1

    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
