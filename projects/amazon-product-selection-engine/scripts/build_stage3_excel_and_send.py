#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path("/Users/mac_claw/.openclaw/workspace")
DEFAULT_METRICS_JSON = ROOT / "data/amazon-product-selection/processed/stage3-amazon-keyword-metrics.json"
DEFAULT_EXPANDED_JSON = ROOT / "data/amazon-product-selection/processed/stage3-amazon-expanded-alternate-metrics.json"
DEFAULT_OUTPUT = ROOT / "output/amazon-product-selection/amazon-product-selection-stage3-full-results.xlsx"
DEFAULT_STATE = ROOT / "projects/amazon-product-selection-engine/runtime/state.json"
OPENCLAW_BIN = "/opt/homebrew/bin/openclaw"
DEFAULT_TELEGRAM_CHAT = "8528973600"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def excel_col_name(index: int) -> str:
    result = ""
    while index > 0:
        index, rem = divmod(index - 1, 26)
        result = chr(65 + rem) + result
    return result


def xml_text(value: Any) -> str:
    return xml_escape("" if value is None else str(value), {'"': "&quot;", "'": "&apos;"})


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def sheet_rows_from_records(headers: list[str], rows: list[dict[str, Any]]) -> list[list[Any]]:
    out: list[list[Any]] = [headers]
    for row in rows:
        out.append([row.get(header, "") for header in headers])
    return out


def column_widths(rows: list[list[Any]]) -> list[float]:
    if not rows:
        return []
    max_cols = max(len(row) for row in rows)
    widths: list[float] = []
    for col_idx in range(max_cols):
        max_len = 0
        for row in rows:
            value = row[col_idx] if col_idx < len(row) else ""
            max_len = max(max_len, min(len("" if value is None else str(value)), 100))
        widths.append(min(max_len + 2, 50))
    return widths


def worksheet_xml(*, rows: list[list[Any]], freeze_header: bool = True) -> str:
    cols_xml = ""
    widths = column_widths(rows)
    if widths:
        col_entries = []
        for idx, width in enumerate(widths, start=1):
            col_entries.append(f'<col min="{idx}" max="{idx}" width="{width:.2f}" customWidth="1"/>')
        cols_xml = f"<cols>{''.join(col_entries)}</cols>"

    sheet_view = ""
    if freeze_header and rows:
        sheet_view = (
            '<sheetViews><sheetView workbookViewId="0">'
            '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
            '<selection pane="bottomLeft" activeCell="A2" sqref="A2"/>'
            "</sheetView></sheetViews>"
        )

    row_entries: list[str] = []
    for row_idx, row in enumerate(rows, start=1):
        cell_entries: list[str] = []
        for col_idx, value in enumerate(row, start=1):
            ref = f"{excel_col_name(col_idx)}{row_idx}"
            style = ' s="1"' if row_idx == 1 else ""
            if value is None or value == "":
                continue
            if is_number(value):
                cell_entries.append(f'<c r="{ref}"{style}><v>{value}</v></c>')
            else:
                cell_entries.append(f'<c r="{ref}" t="inlineStr"{style}><is><t>{xml_text(value)}</t></is></c>')
        row_entries.append(f'<row r="{row_idx}">{"".join(cell_entries)}</row>')
    sheet_data = f"<sheetData>{''.join(row_entries)}</sheetData>"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"{sheet_view}{cols_xml}{sheet_data}</worksheet>"
    )


def styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<fonts count=\"2\">"
        "<font><sz val=\"11\"/><name val=\"Calibri\"/><family val=\"2\"/></font>"
        "<font><b/><color rgb=\"FFFFFFFF\"/><sz val=\"11\"/><name val=\"Calibri\"/><family val=\"2\"/></font>"
        "</fonts>"
        "<fills count=\"3\">"
        "<fill><patternFill patternType=\"none\"/></fill>"
        "<fill><patternFill patternType=\"gray125\"/></fill>"
        "<fill><patternFill patternType=\"solid\"><fgColor rgb=\"FF1F4E78\"/><bgColor indexed=\"64\"/></patternFill></fill>"
        "</fills>"
        "<borders count=\"1\"><border><left/><right/><top/><bottom/><diagonal/></border></borders>"
        "<cellStyleXfs count=\"1\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\"/></cellStyleXfs>"
        "<cellXfs count=\"2\">"
        "<xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\" xfId=\"0\"/>"
        "<xf numFmtId=\"0\" fontId=\"1\" fillId=\"2\" borderId=\"0\" xfId=\"0\" applyFont=\"1\" applyFill=\"1\"/>"
        "</cellXfs>"
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        "</styleSheet>"
    )


def rows_from_payload(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path)
    rows = payload.get("rows") or payload.get("metrics") or []
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def write_xlsx(path: Path, *, metrics_rows: list[dict[str, Any]], expanded_rows: list[dict[str, Any]]) -> None:
    completed = sum(1 for row in metrics_rows if str(row.get("collection_status") or "") in {"ok", "empty"})
    blocked = sum(1 for row in metrics_rows if str(row.get("collection_status") or "") not in {"ok", "empty"})
    summary_rows = [
        ["generated_at", utc_now()],
        ["keyword_row_count", len(metrics_rows)],
        ["completed_keyword_count", completed],
        ["blocked_keyword_count", blocked],
        ["expanded_row_count", len(expanded_rows)],
    ]
    metric_headers = list(metrics_rows[0].keys()) if metrics_rows else []
    expanded_headers = list(expanded_rows[0].keys()) if expanded_rows else []
    sheets = [
        ("Summary", [["Field", "Value"], *summary_rows]),
        ("Keyword Metrics", sheet_rows_from_records(metric_headers, metrics_rows)),
        ("Expanded Entries", sheet_rows_from_records(expanded_headers, expanded_rows)),
    ]

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        + "".join(
            f'<sheet name="{xml_text(name)}" sheetId="{idx}" r:id="rId{idx}"/>'
            for idx, (name, _) in enumerate(sheets, start=1)
        )
        + "</sheets></workbook>"
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{idx}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{idx}.xml"/>'
            for idx in range(1, len(sheets) + 1)
        )
        + f'<Relationship Id="rId{len(sheets)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        + "</Relationships>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        + "".join(
            f'<Override PartName="/xl/worksheets/sheet{idx}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for idx in range(1, len(sheets) + 1)
        )
        + "</Types>"
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/styles.xml", styles_xml())
        for idx, (_, sheet_rows) in enumerate(sheets, start=1):
            zf.writestr(f"xl/worksheets/sheet{idx}.xml", worksheet_xml(rows=sheet_rows))


def send_to_telegram(chat_id: str, text: str, attachment: Path) -> list[dict[str, Any]]:
    deliveries: list[dict[str, Any]] = []
    text_proc = subprocess.run(
        [OPENCLAW_BIN, "message", "send", "--channel", "telegram", "--target", chat_id, "--message", text, "--json"],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    deliveries.append(
        {
            "kind": "text",
            "returncode": text_proc.returncode,
            "stdout": text_proc.stdout,
            "stderr": text_proc.stderr,
        }
    )
    media_proc = subprocess.run(
        [OPENCLAW_BIN, "message", "send", "--channel", "telegram", "--target", chat_id, "--media", str(attachment), "--force-document", "--json"],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    deliveries.append(
        {
            "kind": "media",
            "path": str(attachment),
            "returncode": media_proc.returncode,
            "stdout": media_proc.stdout,
            "stderr": media_proc.stderr,
        }
    )
    return deliveries


def update_runtime_state(state_path: Path, excel_path: Path, deliveries: list[dict[str, Any]]) -> None:
    payload = read_json(state_path) if state_path.exists() else {}
    if not isinstance(payload, dict):
        payload = {}
    stage_status = payload.setdefault("stage_status", {})
    stage3 = stage_status.setdefault("stage_3_amazon_keyword_collection", {})
    stage3["artifact_output_excel"] = str(excel_path)
    stage3["telegram_stage3_excel_deliveries"] = deliveries
    payload["last_updated"] = utc_now()
    write_json(state_path, payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the full stage3 Excel workbook and send it to Telegram.")
    parser.add_argument("--metrics-json", type=Path, default=DEFAULT_METRICS_JSON)
    parser.add_argument("--expanded-json", type=Path, default=DEFAULT_EXPANDED_JSON)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--state-json", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--telegram-chat", default=DEFAULT_TELEGRAM_CHAT)
    parser.add_argument("--send-telegram", action="store_true")
    args = parser.parse_args()

    metrics_rows = rows_from_payload(args.metrics_json)
    expanded_rows = rows_from_payload(args.expanded_json)
    if not metrics_rows:
        raise SystemExit("stage3 metrics rows are empty; cannot build workbook")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_xlsx(args.output, metrics_rows=metrics_rows, expanded_rows=expanded_rows)

    deliveries: list[dict[str, Any]] = []
    if args.send_telegram:
        completed = sum(1 for row in metrics_rows if str(row.get("collection_status") or "") in {"ok", "empty"})
        text = (
            "亚马逊选品 stage3 全量关键词采集已完成。\n"
            f"- 完成关键词数: {completed}\n"
            f"- 展开行数: {len(expanded_rows)}\n"
            f"- 文件: {args.output.name}"
        )
        deliveries = send_to_telegram(args.telegram_chat, text, args.output)

    update_runtime_state(args.state_json, args.output, deliveries)
    print(
        json.dumps(
            {
                "status": "ok",
                "excel_path": str(args.output),
                "telegram_deliveries": deliveries,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
