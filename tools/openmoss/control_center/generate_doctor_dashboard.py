#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from paths import CONTROL_CENTER_RUNTIME_ROOT, DOCTOR_LAST_RUN_PATH


DOCTOR_ROOT = CONTROL_CENTER_RUNTIME_ROOT / "doctor"
HEARTBEAT_LAST_CYCLE_PATH = DOCTOR_ROOT / "heartbeats" / "last_cycle.json"
DASHBOARD_PATH = DOCTOR_ROOT / "dashboard.html"
TASKS_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/autonomy/tasks")
WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
NEOSGO_MARKETING_ROOT = WORKSPACE_ROOT / "projects" / "neosgo-marketing-suite"
NEOSGO_SELLER_STATE_PATH = WORKSPACE_ROOT / "data" / "neosgo-seller-maintenance-state.json"
NEOSGO_SEO_GEO_STATE_PATH = WORKSPACE_ROOT / "projects" / "neosgo-seo-geo-engine" / "runtime" / "state.json"
NEOSGO_MARKETING_GOOGLE_MAPS_REPORT = NEOSGO_MARKETING_ROOT / "output" / "prospect-data-engine" / "google-maps-discovery-report.json"
NEOSGO_MARKETING_GOOGLE_MAPS_EMAIL_REPORT = NEOSGO_MARKETING_ROOT / "output" / "prospect-data-engine" / "google-maps-email-enrichment-report.json"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _badge(text: str, tone: str) -> str:
    return f'<span class="badge badge-{tone}">{html.escape(text)}</span>'


def _tone_for_ratio(value: float) -> str:
    if value >= 0.85:
        return "danger"
    if value >= 0.5:
        return "warn"
    return "ok"


def _tone_for_alignment(name: str) -> str:
    mapping = {
        "aligned": "ok",
        "weak_alignment": "warn",
        "drifting": "warn",
        "mismatch": "danger",
    }
    return mapping.get(name, "muted")


def _tone_for_stage(name: str) -> str:
    mapping = {
        "active": "ok",
        "complete_or_ready_for_completion": "ok",
        "inconsistent": "danger",
        "unknown_stage": "danger",
    }
    return mapping.get(name, "muted")


def _render_count_grid(counts: dict[str, Any], tone_resolver) -> str:
    if not counts:
        return '<div class="empty">No data</div>'
    cards = []
    for key, value in sorted(counts.items(), key=lambda item: (-int(item[1]), item[0])):
        cards.append(
            f"""
            <div class="mini-card">
              <div class="mini-title">{html.escape(str(key))}</div>
              <div class="mini-value">{html.escape(str(value))}</div>
              <div class="mini-badge">{_badge(str(key), tone_resolver(str(key)))}</div>
            </div>
            """
        )
    return '<div class="mini-grid">' + "".join(cards) + "</div>"


def _render_heartbeat_rows(items: list[dict[str, Any]], limit: int = 20) -> str:
    if not items:
        return '<tr><td colspan="6" class="empty-cell">No heartbeat rows</td></tr>'
    rows = []
    for item in items[:limit]:
        goal_alignment = (item.get("goal_alignment", {}) or {}).get("status", "unknown")
        stage_consistency = (item.get("stage_consistency", {}) or {}).get("status", "unknown")
        drift_score = float(item.get("drift_score", 0.0) or 0.0)
        gate = (item.get("completion_gate_status", {}) or {}).get("status", "unknown")
        progress = (item.get("progress_evidence", {}) or {}).get("progress_state", "unknown")
        rows.append(
            f"""
            <tr>
              <td>{html.escape(str(item.get("task_id", "")))}</td>
              <td>{_badge(str(goal_alignment), _tone_for_alignment(str(goal_alignment)))}</td>
              <td>{_badge(str(stage_consistency), _tone_for_stage(str(stage_consistency)))}</td>
              <td>{_badge(f"{drift_score:.3f}", _tone_for_ratio(drift_score))}</td>
              <td>{html.escape(str(gate))}</td>
              <td>{html.escape(str(progress))}</td>
            </tr>
            """
        )
    return "".join(rows)


def _render_doctor_reports(reports: list[dict[str, Any]], limit: int = 12) -> str:
    if not reports:
        return '<div class="empty">No doctor reports</div>'
    cards = []
    for report in reports[:limit]:
        diagnosis = report.get("diagnosis", {}) or {}
        repair = report.get("repair", {}) or {}
        priority = report.get("priority", {}) or {}
        cards.append(
            f"""
            <article class="report-card">
              <div class="report-head">
                <strong>{html.escape(str(diagnosis.get("task_id", report.get("task_id", ""))))}</strong>
                {_badge(str(priority.get("bucket", "unknown")), "muted")}
              </div>
              <div class="report-body">
                <div><span class="label">Reason</span>{html.escape(str(diagnosis.get("reason", "")))}</div>
                <div><span class="label">Stage</span>{html.escape(str(diagnosis.get("current_stage", "")))}</div>
                <div><span class="label">Repair</span>{html.escape(str(repair.get("reason", "")))}</div>
                <div><span class="label">Idle</span>{html.escape(_fmt(diagnosis.get("idle_seconds", 0)))}</div>
              </div>
            </article>
            """
        )
    return '<div class="report-grid">' + "".join(cards) + "</div>"


def _task_row(name: str, status: str, mode: str, detail: str) -> dict[str, str]:
    return {
        "name": name,
        "status": status,
        "mode": mode,
        "detail": detail,
    }


def _workflow_status_tone(status: str) -> str:
    normalized = status.strip().lower()
    if normalized in {"ok", "active", "healthy", "ready", "running", "completed"}:
        return "ok"
    if normalized in {"partial", "waiting", "review", "queued", "triggered"}:
        return "warn"
    if normalized in {"blocked", "failed", "missing_api_key", "error"}:
        return "danger"
    return "muted"


def _workflow_mode_tone(mode: str) -> str:
    normalized = mode.strip().lower()
    if normalized in {"持续进行", "continuous"}:
        return "ok"
    if normalized in {"触发进行", "triggered"}:
        return "warn"
    return "muted"


def _latest_marketing_cycle() -> dict[str, Any]:
    path = NEOSGO_MARKETING_ROOT / "runtime" / "marketing-automation-suite" / "last_cycle.json"
    return _read_json(path)


def _latest_marketing_state() -> dict[str, Any]:
    path = NEOSGO_MARKETING_ROOT / "runtime" / "state.json"
    return _read_json(path)


def _latest_marketing_google_maps_report() -> dict[str, Any]:
    return _read_json(NEOSGO_MARKETING_GOOGLE_MAPS_REPORT)


def _latest_marketing_google_maps_email_report() -> dict[str, Any]:
    return _read_json(NEOSGO_MARKETING_GOOGLE_MAPS_EMAIL_REPORT)


def _latest_seller_state() -> dict[str, Any]:
    return _read_json(NEOSGO_SELLER_STATE_PATH)


def _latest_seo_geo_state() -> dict[str, Any]:
    return _read_json(NEOSGO_SEO_GEO_STATE_PATH)


def _workflow_overview() -> list[dict[str, Any]]:
    marketing_cycle = _latest_marketing_cycle()
    marketing_state = _latest_marketing_state()
    marketing_google_maps_report = _latest_marketing_google_maps_report()
    marketing_google_maps_email_report = _latest_marketing_google_maps_email_report()
    seller_state = _latest_seller_state()
    seo_geo_state = _latest_seo_geo_state()

    marketing_steps = (marketing_cycle.get("steps", {}) or {})
    marketing_report = marketing_cycle.get("report", {}) or {}
    marketing_google_maps = marketing_steps.get("google_maps_discovery", {}) or {}
    marketing_email_enrichment = marketing_steps.get("google_maps_email_enrichment", {}) or {}
    marketing_google_maps_payload = marketing_google_maps_report or (marketing_google_maps.get("payload", {}) or {})
    marketing_email_enrichment_payload = marketing_google_maps_email_report or (marketing_email_enrichment.get("payload", {}) or {})
    marketing_quality = marketing_report.get("quality_gate", {}) or {}
    marketing_strategy = marketing_steps.get("marketing_strategy_tasks", {}) or {}
    marketing_queue = marketing_steps.get("execution_queue", {}) or {}

    seller_scan = seller_state.get("candidate_scan_meta", {}) or {}
    seller_import = seller_state.get("import_phase", {}) or {}
    seller_draft = seller_state.get("draft_phase", {}) or {}
    seller_rejected = seller_state.get("rejected_phase", {}) or {}
    seller_inventory = seller_state.get("inventory_sync_phase", {}) or {}

    seo_runs = list(seo_geo_state.get("runs", []) or [])
    latest_seo_run = seo_runs[-1] if seo_runs else {}

    return [
        {
            "name": "NEOSGO 市场营销工作流",
            "summary": "潜在客户挖掘、数据清洗、客户数据库、定制营销策略与实施队列。",
            "tasks": [
                _task_row(
                    "Google Maps 区域潜客挖掘",
                    (
                        "ok"
                        if marketing_google_maps_payload.get("discovered_count", 0)
                        else (
                            "review"
                            if int(marketing_google_maps_payload.get("failure_count", 0) or 0) > 0
                            else "waiting"
                        )
                    ),
                    "持续进行",
                    f"最近一轮：{marketing_google_maps_payload.get('discovered_count', 0)} 家，失败 query={marketing_google_maps_payload.get('failure_count', 0)}，本轮 query={marketing_google_maps_payload.get('scheduled_query_count', '-')}",
                ),
                _task_row(
                    "官网访问与邮箱抓取/校验",
                    (
                        "ok"
                        if int(marketing_email_enrichment_payload.get("validated_email_count", 0) or 0) > 0
                        else ("review" if int(marketing_email_enrichment_payload.get("deferred_count", 0) or 0) > 0 else "waiting")
                    ),
                    "持续进行",
                    f"最近一轮：提取 {marketing_email_enrichment_payload.get('email_candidate_count', 0)} 个邮箱候选，验证通过 {marketing_email_enrichment_payload.get('validated_email_count', 0)} 个，待补抓 {marketing_email_enrichment_payload.get('deferred_count', 0)} 个站点",
                ),
                _task_row(
                    "客户数据库维护",
                    "ok" if str(marketing_quality.get("status", "")).strip().lower() == "pass" else "review",
                    "持续进行",
                    f"质量门：{marketing_quality.get('status', '-')}，策略可用：{marketing_quality.get('allowed_for_strategy', '-')}",
                ),
                _task_row(
                    "创建定制营销方案",
                    "ok" if marketing_strategy.get("ok") else "triggered",
                    "触发进行",
                    f"最近一轮策略任务：{marketing_strategy.get('payload', {}).get('task_count', 0)} 条",
                ),
                _task_row(
                    "实施营销与反馈回流",
                    "ok" if marketing_queue.get("ok") else "triggered",
                    "触发进行",
                    f"执行队列：{marketing_queue.get('payload', {}).get('queued_count', 0)} 条；项目状态：{marketing_state.get('status', '-')}",
                ),
            ],
        },
        {
            "name": "NEOSGO Seller 维护工作流",
            "summary": "GIGA 候选扫描、NEW_IMPORT 导入、DRAFT/REJECTED 处理与库存同步。",
            "tasks": [
                _task_row(
                    "扫描 GIGA candidates",
                    "ok",
                    "持续进行",
                    f"模式：{seller_scan.get('mode', '-')}；本轮扫描页数：{seller_scan.get('pages_scanned', '-')}",
                ),
                _task_row(
                    "导入新的未导入产品",
                    "ok" if int(seller_import.get("failureCount", 0) or 0) == 0 else "review",
                    "触发进行",
                    f"eligible={seller_import.get('eligibleCount', 0)}，processed={seller_import.get('processedCount', 0)}，failure={seller_import.get('failureCount', 0)}",
                ),
                _task_row(
                    "优化 DRAFT 并提交审核",
                    "ok" if int(seller_draft.get("blocked_count", 0) or 0) == 0 else "review",
                    "触发进行",
                    f"enumerated={seller_draft.get('enumerated_count', 0)}，submitted={seller_draft.get('submitted_count', 0)}",
                ),
                _task_row(
                    "重提 REJECTED listing",
                    "ok" if int(seller_rejected.get("blocked_count", 0) or 0) == 0 else "review",
                    "触发进行",
                    f"enumerated={seller_rejected.get('enumerated_count', 0)}，submitted={seller_rejected.get('submitted_count', 0)}",
                ),
                _task_row(
                    "同步已上传 listing 库存",
                    "ok",
                    "持续进行",
                    f"processed={seller_inventory.get('processed_count', 0)}，patched={seller_inventory.get('patched_count', 0)}",
                ),
            ],
        },
        {
            "name": "NEOSGO SEO + GEO 工作流",
            "summary": "GSC 同步、反馈蒸馏、研究选题、内容生成与发布。",
            "tasks": [
                _task_row(
                    "同步 GSC 与反馈",
                    "ok" if latest_seo_run else "waiting",
                    "持续进行",
                    f"最近 run：{latest_seo_run.get('run_id', '-')}；feedback rows={latest_seo_run.get('feedback_row_count', '-')}",
                ),
                _task_row(
                    "研究与主题选择",
                    "ok" if latest_seo_run else "waiting",
                    "持续进行",
                    f"primary focus={latest_seo_run.get('primary_focus_topic', '-')}",
                ),
                _task_row(
                    "内容与 GEO 发布/回填",
                    "ok" if latest_seo_run and not latest_seo_run.get('blocked') else "review",
                    "触发进行",
                    f"writes={latest_seo_run.get('writes_count', '-')}，gap={latest_seo_run.get('gap_count', '-')}",
                ),
            ],
        },
    ]


def _render_workflow_rows(items: list[dict[str, str]]) -> str:
    if not items:
        return '<tr><td colspan="4" class="empty-cell">No workflow tasks</td></tr>'
    rows = []
    for index, item in enumerate(items, start=1):
        rows.append(
            f"""
            <tr>
              <td>{index}</td>
              <td>{html.escape(item.get("name", ""))}</td>
              <td>{_badge(item.get("mode", ""), _workflow_mode_tone(item.get("mode", "")))}</td>
              <td>{_badge(item.get("status", ""), _workflow_status_tone(item.get("status", "")))}</td>
              <td>{html.escape(item.get("detail", ""))}</td>
            </tr>
            """
        )
    return "".join(rows)


def _render_workflow_section(workflows: list[dict[str, Any]]) -> str:
    if not workflows:
        return '<div class="empty">No workflow data</div>'
    parts = []
    for workflow in workflows:
        parts.append(
            f"""
            <div class="card workflow-card">
              <div class="workflow-head">
                <div>
                  <h3 class="workflow-title">{html.escape(workflow.get("name", ""))}</h3>
                  <p class="workflow-summary">{html.escape(workflow.get("summary", ""))}</p>
                </div>
              </div>
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>任务</th>
                    <th>类型</th>
                    <th>状态</th>
                    <th>说明</th>
                  </tr>
                </thead>
                <tbody>
                  {_render_workflow_rows(workflow.get("tasks", []))}
                </tbody>
              </table>
            </div>
            """
        )
    return "".join(parts)


def _collect_complex_task_overview(limit: int = 18) -> dict[str, Any]:
    total = 0
    healthy = 0
    blocked = 0
    missing_artifacts = 0
    rows: list[dict[str, Any]] = []
    if not TASKS_ROOT.exists():
        return {"total": 0, "healthy": 0, "blocked": 0, "missing_artifacts": 0, "rows": []}
    for task_dir in sorted(TASKS_ROOT.iterdir(), key=lambda p: p.name):
        contract = _read_json(task_dir / "contract.json")
        state = _read_json(task_dir / "state.json")
        if not contract or not state:
            continue
        controller = (((contract.get("metadata", {}) or {}).get("control_center", {}) or {}).get("complex_task_controller", {}) or {})
        if not controller.get("enabled"):
            continue
        total += 1
        heartbeat = ((state.get("metadata", {}) or {}).get("doctor_heartbeat", {}) or {})
        gate_raw = heartbeat.get("completion_gate_status", {}) if isinstance(heartbeat, dict) else {}
        if isinstance(gate_raw, dict):
            completion_gate = str(gate_raw.get("status", "unknown") or "unknown")
        else:
            completion_gate = str(gate_raw or "unknown")
        stage_name = str(state.get("current_stage", "") or "")
        artifact_keys = sorted(list((((state.get("metadata", {}) or {}).get("stage_artifacts", {}) or {}).keys())))
        if completion_gate in {"ok", "not_applicable"}:
            healthy += 1
        else:
            blocked += 1
        if stage_name and stage_name not in artifact_keys and stage_name != "verify":
            missing_artifacts += 1
        if len(rows) < limit:
            rows.append(
                {
                    "task_id": task_dir.name,
                    "status": str(state.get("status", "") or ""),
                    "current_stage": stage_name,
                    "completion_gate": completion_gate,
                    "artifact_count": len(artifact_keys),
                    "artifact_keys": artifact_keys,
                }
            )
    return {
        "total": total,
        "healthy": healthy,
        "blocked": blocked,
        "missing_artifacts": missing_artifacts,
        "rows": rows,
    }


def _tone_for_gate(name: str) -> str:
    mapping = {
        "ok": "ok",
        "not_applicable": "muted",
        "blocked_by_missing_postmortem": "danger",
        "blocked_by_required_milestones": "danger",
        "unknown": "warn",
    }
    return mapping.get(name, "warn")


def _render_complex_rows(items: list[dict[str, Any]]) -> str:
    if not items:
        return '<tr><td colspan="6" class="empty-cell">No complex task rows</td></tr>'
    rows = []
    for item in items:
        rows.append(
            f"""
            <tr>
              <td>{html.escape(str(item.get("task_id", "")))}</td>
              <td>{html.escape(str(item.get("status", "")))}</td>
              <td>{html.escape(str(item.get("current_stage", "")))}</td>
              <td>{_badge(str(item.get("completion_gate", "")), _tone_for_gate(str(item.get("completion_gate", ""))))}</td>
              <td>{html.escape(str(item.get("artifact_count", 0)))}</td>
              <td>{html.escape(", ".join(item.get("artifact_keys", []) or []))}</td>
            </tr>
            """
        )
    return "".join(rows)


def build_dashboard() -> str:
    last_run = _read_json(DOCTOR_LAST_RUN_PATH)
    last_cycle = _read_json(HEARTBEAT_LAST_CYCLE_PATH)

    doctor_heartbeat = last_run.get("doctor_heartbeat", {}) or {}
    stability = last_run.get("stability_overview", {}) or {}
    reports = list(last_run.get("reports", []) or [])
    heartbeat_items = list(last_cycle.get("items", []) or [])
    complex_overview = _collect_complex_task_overview()

    heartbeat_total = int(stability.get("heartbeat_total", doctor_heartbeat.get("count", 0)) or 0)
    needs_intervention_total = int(stability.get("needs_intervention_total", 0) or 0)
    drift_detected_total = int(stability.get("drift_detected_total", 0) or 0)
    avg_drift_score = float(stability.get("average_drift_score", 0.0) or 0.0)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="30">
  <title>JinClaw Doctor Dashboard</title>
  <style>
    :root {{
      --bg: #f3efe5;
      --paper: #fffdf8;
      --ink: #1f1b18;
      --muted: #6c635b;
      --line: #d9cfc1;
      --ok: #1f7a55;
      --warn: #a86812;
      --danger: #a53d2d;
      --accent: #0e5a8a;
      --shadow: 0 10px 30px rgba(38, 28, 18, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(14, 90, 138, 0.12), transparent 34%),
        radial-gradient(circle at top right, rgba(168, 104, 18, 0.10), transparent 28%),
        linear-gradient(180deg, #f8f4ec 0%, var(--bg) 100%);
    }}
    .wrap {{
      max-width: 1360px;
      margin: 0 auto;
      padding: 32px 24px 56px;
    }}
    .hero {{
      background: linear-gradient(135deg, rgba(255,255,255,.94), rgba(255,250,242,.88));
      border: 1px solid rgba(217, 207, 193, 0.9);
      border-radius: 24px;
      box-shadow: var(--shadow);
      padding: 28px 28px 20px;
      margin-bottom: 24px;
    }}
    .eyebrow {{
      color: var(--accent);
      letter-spacing: 0.08em;
      text-transform: uppercase;
      font-size: 12px;
      font-weight: 700;
      margin-bottom: 10px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 40px;
      line-height: 1.05;
    }}
    .sub {{
      color: var(--muted);
      font-size: 16px;
      max-width: 860px;
      line-height: 1.55;
    }}
    .meta {{
      margin-top: 16px;
      color: var(--muted);
      font-size: 14px;
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
      margin: 24px 0;
    }}
    .card {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 20px;
      box-shadow: var(--shadow);
      padding: 18px 18px 16px;
    }}
    .stat-label {{
      color: var(--muted);
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: .05em;
      margin-bottom: 10px;
    }}
    .stat-value {{
      font-size: 34px;
      font-weight: 700;
      margin-bottom: 8px;
    }}
    .section {{
      margin-top: 26px;
      display: grid;
      gap: 18px;
    }}
    .section-title {{
      font-size: 24px;
      margin: 0;
    }}
    .section-sub {{
      color: var(--muted);
      font-size: 14px;
      margin: 0;
    }}
    .grid-2 {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
    }}
    .mini-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 12px;
    }}
    .mini-card {{
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px;
      background: rgba(255,255,255,0.65);
    }}
    .mini-title {{
      font-size: 12px;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 8px;
    }}
    .mini-value {{
      font-size: 26px;
      font-weight: 700;
      margin-bottom: 8px;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid currentColor;
    }}
    .badge-ok {{ color: var(--ok); background: rgba(31,122,85,.08); }}
    .badge-warn {{ color: var(--warn); background: rgba(168,104,18,.10); }}
    .badge-danger {{ color: var(--danger); background: rgba(165,61,45,.10); }}
    .badge-muted {{ color: var(--muted); background: rgba(108,99,91,.08); }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      text-align: left;
      padding: 12px 10px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      text-transform: uppercase;
      font-size: 12px;
      letter-spacing: .05em;
    }}
    .report-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 14px;
    }}
    .workflow-card {{
      padding: 18px 18px 10px;
    }}
    .workflow-head {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      margin-bottom: 12px;
    }}
    .workflow-title {{
      margin: 0 0 6px;
      font-size: 21px;
    }}
    .workflow-summary {{
      margin: 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.45;
    }}
    .report-card {{
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.75);
      border-radius: 18px;
      padding: 16px;
    }}
    .report-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      margin-bottom: 12px;
    }}
    .report-body {{
      display: grid;
      gap: 8px;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.45;
    }}
    .label {{
      display: inline-block;
      min-width: 78px;
      color: var(--ink);
      font-weight: 700;
    }}
    .empty, .empty-cell {{
      color: var(--muted);
      text-align: center;
      padding: 24px 0;
    }}
    @media (max-width: 980px) {{
      .grid-2 {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 32px; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div class="eyebrow">JinClaw Stability Console</div>
      <h1>Doctor Dashboard</h1>
      <p class="sub">
        A local, static operations board for JinClaw's doctor coverage, heartbeat health,
        reroute guards, rollback safety, and task stability signals.
      </p>
      <div class="meta">
        <span>Checked at: {html.escape(_fmt(last_run.get("checked_at")))}</span>
        <span>Heartbeat cycle: {html.escape(_fmt(last_cycle.get("written_at")))}</span>
        <span>Source: {html.escape(str(DOCTOR_LAST_RUN_PATH))}</span>
      </div>
    </section>

    <section class="stats">
      <div class="card">
        <div class="stat-label">Active Heartbeats</div>
        <div class="stat-value">{heartbeat_total}</div>
        {_badge('heartbeat coverage', 'ok')}
      </div>
      <div class="card">
        <div class="stat-label">Needs Intervention</div>
        <div class="stat-value">{needs_intervention_total}</div>
        {_badge('doctor queue pressure', 'warn' if needs_intervention_total else 'ok')}
      </div>
      <div class="card">
        <div class="stat-label">Drift Detected</div>
        <div class="stat-value">{drift_detected_total}</div>
        {_badge('alignment risk', 'danger' if drift_detected_total else 'ok')}
      </div>
      <div class="card">
        <div class="stat-label">Average Drift Score</div>
        <div class="stat-value">{avg_drift_score:.3f}</div>
        {_badge('risk temperature', _tone_for_ratio(avg_drift_score))}
      </div>
    </section>

    <section class="section">
      <div>
        <h2 class="section-title">Workflow Board</h2>
        <p class="section-sub">按工作流分级展示任务清单、顺序、当前状态，以及“持续进行 / 触发进行”类型。</p>
      </div>
      {_render_workflow_section(_workflow_overview())}
    </section>

    <section class="section">
      <div>
        <h2 class="section-title">Complex Task Control</h2>
        <p class="section-sub">Complex delivery missions, their current stage, release-gate status, and staged artifact coverage.</p>
      </div>
      <section class="stats">
        <div class="card">
          <div class="stat-label">Complex Tasks</div>
          <div class="stat-value">{complex_overview["total"]}</div>
          {_badge('complex mission coverage', 'ok')}
        </div>
        <div class="card">
          <div class="stat-label">Gate Healthy</div>
          <div class="stat-value">{complex_overview["healthy"]}</div>
          {_badge('ready to continue', 'ok')}
        </div>
        <div class="card">
          <div class="stat-label">Gate Blocked</div>
          <div class="stat-value">{complex_overview["blocked"]}</div>
          {_badge('needs remediation', 'warn' if complex_overview["blocked"] else 'ok')}
        </div>
        <div class="card">
          <div class="stat-label">Missing Stage Artifacts</div>
          <div class="stat-value">{complex_overview["missing_artifacts"]}</div>
          {_badge('artifact pressure', 'danger' if complex_overview["missing_artifacts"] else 'ok')}
        </div>
      </section>
      <div class="card">
        <table>
          <thead>
            <tr>
              <th>Task</th>
              <th>Status</th>
              <th>Current Stage</th>
              <th>Completion Gate</th>
              <th>Artifact Count</th>
              <th>Artifact Keys</th>
            </tr>
          </thead>
          <tbody>
            {_render_complex_rows(complex_overview["rows"])}
          </tbody>
        </table>
      </div>
    </section>

    <section class="section">
      <div>
        <h2 class="section-title">Stability Overview</h2>
        <p class="section-sub">Aggregated signal counts from the latest doctor cycle.</p>
      </div>
      <div class="grid-2">
        <div class="card">
          <h3>Goal Alignment</h3>
          {_render_count_grid(stability.get("goal_alignment_counts", {}) or {{}}, _tone_for_alignment)}
        </div>
        <div class="card">
          <h3>Stage Consistency</h3>
          {_render_count_grid(stability.get("stage_consistency_counts", {}) or {{}}, _tone_for_stage)}
        </div>
      </div>
      <div class="grid-2">
        <div class="card">
          <h3>Completion Gates</h3>
          {_render_count_grid(stability.get("completion_gate_counts", {}) or {{}}, lambda _: 'muted')}
        </div>
        <div class="card">
          <h3>Doctor Cycle</h3>
          <div class="mini-grid">
            <div class="mini-card">
              <div class="mini-title">Processed Total</div>
              <div class="mini-value">{html.escape(_fmt(((last_run.get("doctor_cycle_stats", {}) or {}).get("processed_total"))))}</div>
            </div>
            <div class="mini-card">
              <div class="mini-title">Skipped Total</div>
              <div class="mini-value">{html.escape(_fmt(((last_run.get("doctor_cycle_stats", {}) or {}).get("skipped_total"))))}</div>
            </div>
            <div class="mini-card">
              <div class="mini-title">Heartbeat Errors</div>
              <div class="mini-value">{html.escape(_fmt((doctor_heartbeat.get("error_count"))))}</div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="section">
      <div>
        <h2 class="section-title">Heartbeat Sample</h2>
        <p class="section-sub">First 20 task heartbeats from the latest cycle.</p>
      </div>
      <div class="card">
        <table>
          <thead>
            <tr>
              <th>Task</th>
              <th>Goal Alignment</th>
              <th>Stage Consistency</th>
              <th>Drift Score</th>
              <th>Completion Gate</th>
              <th>Progress</th>
            </tr>
          </thead>
          <tbody>
            {_render_heartbeat_rows(heartbeat_items, limit=20)}
          </tbody>
        </table>
      </div>
    </section>

    <section class="section">
      <div>
        <h2 class="section-title">Doctor Reports</h2>
        <p class="section-sub">Recent intervention summaries from the latest doctor run.</p>
      </div>
      {_render_doctor_reports(reports, limit=12)}
    </section>
  </div>
</body>
</html>
"""


def main() -> int:
    DASHBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD_PATH.write_text(build_dashboard(), encoding="utf-8")
    print(str(DASHBOARD_PATH))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
