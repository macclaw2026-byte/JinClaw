#!/usr/bin/env python3

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
