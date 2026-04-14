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
from typing import Any, Dict, List

from paths import TASK_BOARD_DASHBOARD_PATH


def _clip(value: Any, limit: int = 120) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _badge(text: str, tone: str) -> str:
    return f'<span class="badge badge-{tone}">{html.escape(text)}</span>'


def _attr(value: Any) -> str:
    return html.escape(str(value or "").strip(), quote=True)


def _search_blob(*parts: Any) -> str:
    return " ".join(" ".join(str(part or "").split()) for part in parts if str(part or "").strip())


def _status_rank(status: str) -> int:
    normalized = str(status or "").strip().lower()
    order = {
        "running": 0,
        "planning": 1,
        "waiting_external": 2,
        "blocked": 3,
        "completed": 4,
        "failed": 5,
        "lost": 6,
        "cancelled": 7,
    }
    return order.get(normalized, 9)


def _priority_rank(priority: str) -> int:
    normalized = str(priority or "").strip().lower()
    order = {
        "critical": 4,
        "high": 3,
        "medium": 2,
        "low": 1,
    }
    return order.get(normalized, 0)


def _tone_for_status(status: str, *, needs_intervention: bool = False) -> str:
    normalized = str(status or "").strip().lower()
    if needs_intervention:
        return "danger"
    if normalized in {"running", "planning", "waiting_external"}:
        return "ok"
    if normalized in {"blocked"}:
        return "warn"
    if normalized in {"completed"}:
        return "muted"
    if normalized in {"failed", "lost", "cancelled"}:
        return "danger"
    return "muted"


def _tone_for_runtime_family(family: str) -> str:
    normalized = str(family or "").strip().lower()
    if normalized == "running":
        return "ok"
    if normalized == "attention":
        return "warn"
    if normalized == "not_loaded":
        return "danger"
    return "muted"


def _tone_for_incident_severity(severity: str) -> str:
    normalized = str(severity or "").strip().lower()
    if normalized in {"critical", "high"}:
        return "danger"
    if normalized in {"medium", "warn", "warning"}:
        return "warn"
    if normalized in {"resolved", "ok"}:
        return "ok"
    return "muted"


def _incident_scope_label(scope: str) -> str:
    normalized = str(scope or "").strip().lower()
    if normalized == "process_incident":
        return "Process"
    if normalized == "task_incident":
        return "Task"
    return normalized or "Unknown"


def _render_usage_examples() -> str:
    examples = [
        "[task:JC10012] 继续推进并告诉我现在卡点",
        "任务: JC10018 | 现在进度怎么样",
        "[task:JC10018-3] 继续处理这个子任务",
    ]
    chips = "".join(f"<code>{html.escape(example)}</code>" for example in examples)
    return f'<div class="usage-chips">{chips}</div>'


def _render_blocked_summary(summary: Dict[str, Any]) -> str:
    total = int(summary.get("blocked_total", 0) or 0)
    categories = summary.get("blocked_categories", {}) or {}
    chips = []
    labels = {
        "project_crawler_remediation": "等待 crawler 修复",
        "targeted_fix": "旧任务已被后续任务替代",
        "session_binding": "没有绑定到有效会话",
        "runtime_or_contract_fix": "运行时或 contract 需要修",
        "approval_or_contract": "需要审批或 contract 修正",
    }
    for key, label in labels.items():
        count = int(categories.get(key, 0) or 0)
        if count <= 0:
            continue
        chips.append(f"<span class=\"explain-chip\"><strong>{count}</strong> {html.escape(label)}</span>")
    if not chips:
        chips.append("<span class=\"explain-chip\">当前没有 blocked 任务</span>")
    return f"""
    <div class="explain-card">
      <div class="explain-title">Why So Many Blocked Tasks?</div>
      <p><strong>{total}</strong> 个任务显示为 <code>blocked</code>，这里的 blocked 主要表示“当前被系统判定为暂停/等待/已被后续任务接管”，不等于失败。</p>
      <div class="explain-chip-row">{''.join(chips)}</div>
    </div>
    """


def _render_module_guide() -> str:
    items = [
        ("AI Incident Inbox", "看 doctor 刚发现了哪些 process/task incident、AI 是否已经接管、最近又修好了哪些事故。遇到系统异常时先看这里。"),
        ("Scheduler & Services", "最上面的模块会告诉你机器上实际安装了哪些定时任务、哪些是常驻服务、它们何时触发以及现在是否在跑。"),
        ("Conversation Focus", "看每个聊天入口当前实际绑着哪个任务。你要跟我聊哪条任务，先看这里。"),
        ("Task Directory", "按任务组列出 root 任务、当前节点和任务用途。最适合回答“这个任务到底是干什么的”。"),
        ("Canonical Tasks", "当前控制平面认定的主任务视图，便于看状态、阶段、下一步和聊天绑定数。"),
        ("Waiting", "这些任务不是在跑，而是在等外部条件，例如审批、会话、运行时信号。"),
        ("Needs Attention", "医生队列。这里优先展示最值得先处理的卡点任务。"),
        ("Archive & Memory", "已完成或确认僵尸化的任务会先蒸馏成摘要，写回记忆，再移入归档区，不会直接硬删除。"),
    ]
    cards = "".join(
        f"""
        <div class="guide-card">
          <div class="guide-title">{html.escape(title)}</div>
          <p>{html.escape(text)}</p>
        </div>
        """
        for title, text in items
    )
    return f'<section class="guide-grid">{cards}</section>'


def _render_table_controls(
    table_id: str,
    *,
    placeholder: str,
    sort_options: List[tuple[str, str]],
    filter_key: str = "",
    filter_label: str = "",
    filter_options: List[tuple[str, str]] | None = None,
    default_sort: str = "order:asc",
) -> str:
    filter_html = ""
    if filter_key:
        options = "".join(
            f'<option value="{_attr(value)}">{html.escape(label)}</option>'
            for value, label in ([("", f"All {filter_label or filter_key.title()}")] + list(filter_options or []))
        )
        filter_html = f"""
        <label class="table-control">
          <span>{html.escape(filter_label or filter_key.title())}</span>
          <select data-table-filter="{_attr(table_id)}" data-filter-key="{_attr(filter_key)}">
            {options}
          </select>
        </label>
        """
    sort_html = "".join(
        f'<option value="{_attr(value)}"{(" selected" if value == default_sort else "")}>{html.escape(label)}</option>'
        for value, label in sort_options
    )
    return f"""
    <div class="table-tools" data-table-controls="{_attr(table_id)}">
      <label class="table-control table-control-search">
        <span>Search</span>
        <input type="search" placeholder="{_attr(placeholder)}" data-table-search="{_attr(table_id)}">
      </label>
      {filter_html}
      <label class="table-control">
        <span>Sort</span>
        <select data-table-sort="{_attr(table_id)}" data-default-sort="{_attr(default_sort)}">
          {sort_html}
        </select>
      </label>
      <button type="button" class="table-reset" data-table-reset="{_attr(table_id)}">Reset</button>
      <span class="table-meta" data-table-meta="{_attr(table_id)}"></span>
    </div>
    """


def _render_focus_rows(items: List[Dict[str, Any]], *, limit: int = 200) -> str:
    if not items:
        return '<tr><td colspan="8" class="empty-cell">No conversation bindings</td></tr>'
    rows = []
    for item in items[:limit]:
        selector_hint = str(item.get("selector_hint", "")).strip()
        example = f"{selector_hint}继续处理这个任务" if selector_hint else "-"
        group_alias = str(item.get("canonical_task_group_alias", "")).strip() or "-"
        task_alias = str(item.get("canonical_task_alias", "")).strip() or "-"
        status = str(item.get("status", "unknown")).strip() or "unknown"
        stage = str(item.get("current_stage", "")).strip() or "-"
        search = _search_blob(
            item.get("conversation_label", ""),
            group_alias,
            task_alias,
            item.get("canonical_task_id", "") or item.get("bound_task_id", ""),
            status,
            stage,
            item.get("next_action", ""),
            item.get("last_goal", "") or item.get("goal", ""),
        )
        rows.append(
            f"""
            <tr data-row="true" data-order="{len(rows)}" data-search="{_attr(search)}" data-conversation="{_attr(item.get('conversation_label', ''))}" data-group="{_attr(group_alias)}" data-task="{_attr(item.get('canonical_task_id', '') or item.get('bound_task_id', ''))}" data-status="{_attr(status)}" data-status-rank="{_status_rank(status)}" data-stage="{_attr(stage)}">
              <td>{html.escape(str(item.get("conversation_label", "")))}</td>
              <td><code>{html.escape(group_alias)}</code><br><code>{html.escape(task_alias)}</code></td>
              <td>{html.escape(str(item.get("canonical_task_id", "") or item.get("bound_task_id", "")))}</td>
              <td>{_badge(status, _tone_for_status(str(item.get("status", "")), needs_intervention=bool(item.get("needs_intervention"))))}</td>
              <td>{html.escape(stage)}</td>
              <td>{html.escape(str(item.get("next_action", "")) or "-")}</td>
              <td title="{html.escape(str(item.get('last_goal', '') or item.get('goal', '')))}">{html.escape(_clip(item.get('last_goal', '') or item.get('goal', ''), 90) or "-")}</td>
              <td><code>{html.escape(example)}</code></td>
            </tr>
            """
        )
    return "".join(rows)


def _render_incident_rows(doctor_incident_inbox: Dict[str, Any], *, limit: int = 200) -> str:
    items = doctor_incident_inbox.get("active_items", []) or []
    if not items:
        return '<tr><td colspan="7" class="empty-cell">No active AI incidents</td></tr>'
    rows = []
    for item in items[:limit]:
        scope = _incident_scope_label(str(item.get("scope", "")))
        severity = str(item.get("severity", "")).strip() or "unknown"
        subject = str(item.get("subject_id", "")).strip() or "-"
        status = str(item.get("status", "")).strip() or "-"
        reason = str(item.get("reason", "")).strip() or "-"
        watch_task_id = str(item.get("watch_task_id", "")).strip()
        watch_status = item.get("watch_status", {}) or {}
        ai_state = str(watch_status.get("status", "")).strip() or ("not yet attached" if not watch_task_id else "unknown")
        ai_stage = str(watch_status.get("current_stage", "")).strip() or "-"
        ai_next_action = str(watch_status.get("next_action", "")).strip() or "-"
        search = _search_blob(
            scope,
            severity,
            subject,
            item.get("name", ""),
            status,
            reason,
            watch_task_id,
            ai_state,
            ai_stage,
            ai_next_action,
        )
        rows.append(
            f"""
            <tr data-row="true" data-order="{len(rows)}" data-search="{_attr(search)}" data-scope="{_attr(scope)}" data-severity="{_attr(severity)}" data-generated="{_attr(item.get('generated_at', ''))}" data-subject="{_attr(subject)}">
              <td>{_badge(scope, "muted")}</td>
              <td><code>{html.escape(subject)}</code><div class="cell-note">{html.escape(_clip(item.get("name", ""), 70) or "-")}</div></td>
              <td>{_badge(severity, _tone_for_incident_severity(severity))}</td>
              <td>{html.escape(status)}</td>
              <td title="{html.escape(reason)}">{html.escape(_clip(reason, 110))}</td>
              <td><code>{html.escape(watch_task_id or "-")}</code><div class="cell-note">{html.escape(str(item.get("watch_task_action", "")).strip() or "pending dispatch")}</div></td>
              <td><strong>{html.escape(ai_state)}</strong><div class="cell-note">{html.escape(ai_stage)} · {html.escape(_clip(ai_next_action, 90))}</div></td>
            </tr>
            """
        )
    return "".join(rows)


def _render_resolution_rows(doctor_incident_inbox: Dict[str, Any], *, limit: int = 50) -> str:
    items = doctor_incident_inbox.get("resolution_items", []) or []
    if not items:
        return '<tr><td colspan="6" class="empty-cell">No recent doctor resolutions</td></tr>'
    rows = []
    for item in items[:limit]:
        scope = _incident_scope_label(str(item.get("scope", "")))
        subject = str(item.get("subject_id", "")).strip() or "-"
        reason = str(item.get("resolution_reason", "")).strip() or "-"
        reusable_rule = str(item.get("reusable_rule", "")).strip() or "-"
        watch_task_id = str(item.get("watch_task_id", "")).strip() or "-"
        change_count = len([change for change in (item.get("suggested_runtime_changes", []) or []) if str(change).strip()])
        search = _search_blob(scope, subject, reason, reusable_rule, watch_task_id, " ".join(item.get("suggested_runtime_changes", []) or []))
        rows.append(
            f"""
            <tr data-row="true" data-order="{len(rows)}" data-search="{_attr(search)}" data-scope="{_attr(scope)}" data-written-at="{_attr(item.get('written_at', ''))}" data-subject="{_attr(subject)}">
              <td>{html.escape(str(item.get("written_at", "")) or "-")}</td>
              <td>{_badge(scope, "muted")}</td>
              <td><code>{html.escape(subject)}</code><div class="cell-note"><code>{html.escape(watch_task_id)}</code></div></td>
              <td title="{html.escape(reason)}">{html.escape(_clip(reason, 90))}</td>
              <td title="{html.escape(reusable_rule)}">{html.escape(_clip(reusable_rule, 120))}</td>
              <td>{change_count}<div class="cell-note">{html.escape(_clip(item.get("evolution_proposal_path", "") or "-", 80))}</div></td>
            </tr>
            """
        )
    return "".join(rows)


def _render_group_rows(task_alias_registry: Dict[str, Any], *, limit: int = 500) -> str:
    groups = task_alias_registry.get("items", []) or []
    if not groups:
        return '<tr><td colspan="6" class="empty-cell">No task groups</td></tr>'
    rows = []
    for group in groups[:limit]:
        items = group.get("items", []) or []
        root_row = next((item for item in items if item.get("is_group_root")), items[-1] if items else {})
        current_row = next((item for item in items if item.get("is_group_current")), root_row)
        group_alias = str(group.get("group_alias", "")).strip() or "-"
        root_task_id = str(group.get("root_task_id", "")).strip() or "-"
        current_task_id = str((current_row or {}).get("task_id", "")).strip() or "-"
        current_task_alias = str((current_row or {}).get("task_alias", "")).strip() or "-"
        status = str((current_row or {}).get("status", "unknown")).strip() or "unknown"
        stage = str((current_row or {}).get("current_stage", "")).strip() or "-"
        goal = str((root_row or {}).get("goal", "")).strip()
        search = _search_blob(group_alias, root_task_id, current_task_alias, current_task_id, status, stage, goal)
        rows.append(
            f"""
            <tr data-row="true" data-order="{len(rows)}" data-search="{_attr(search)}" data-group="{_attr(group_alias)}" data-root="{_attr(root_task_id)}" data-current="{_attr(current_task_id)}" data-status="{_attr(status)}" data-status-rank="{_status_rank(status)}" data-stage="{_attr(stage)}">
              <td><code>{html.escape(group_alias)}</code></td>
              <td>{html.escape(root_task_id)}</td>
              <td><code>{html.escape(current_task_alias)}</code><br>{html.escape(current_task_id)}</td>
              <td>{_badge(status, _tone_for_status(status, needs_intervention=False))}</td>
              <td>{html.escape(stage)}</td>
              <td title="{html.escape(goal)}">{html.escape(_clip(goal, 140) or "-")}</td>
            </tr>
            """
        )
    return "".join(rows)


def _canonical_task_rows(task_registry: Dict[str, Any]) -> List[Dict[str, Any]]:
    canonical_index: Dict[str, Dict[str, Any]] = {}
    for item in task_registry.get("items", []) or []:
        task_id = str(item.get("task_id", "")).strip()
        canonical_task_id = str(item.get("canonical_task_id", "")).strip() or task_id
        if not canonical_task_id:
            continue
        existing = canonical_index.get(canonical_task_id)
        if existing is None or task_id == canonical_task_id:
            canonical_index[canonical_task_id] = item

    status_rank = {
        "running": 0,
        "planning": 1,
        "waiting_external": 2,
        "blocked": 3,
        "completed": 4,
        "failed": 5,
    }
    rows = list(canonical_index.values())
    rows.sort(
        key=lambda item: (
            status_rank.get(str(item.get("status", "")).strip(), 9),
            1 if item.get("needs_intervention") else 0,
            str(item.get("last_progress_at", "") or item.get("last_update_at", "")),
            str(item.get("canonical_task_id", "") or item.get("task_id", "")),
        )
    )
    return rows


def _conversation_count_map(conversation_registry: Dict[str, Any]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in conversation_registry.get("items", []) or []:
        canonical_task_id = str(item.get("canonical_task_id", "")).strip()
        if canonical_task_id:
            counts[canonical_task_id] = counts.get(canonical_task_id, 0) + 1
    return counts


def _render_task_rows(task_registry: Dict[str, Any], conversation_registry: Dict[str, Any], *, limit: int = 500) -> str:
    rows = _canonical_task_rows(task_registry)
    if not rows:
        return '<tr><td colspan="10" class="empty-cell">No tracked tasks</td></tr>'
    conversation_counts = _conversation_count_map(conversation_registry)
    rendered = []
    for item in rows[:limit]:
        canonical_task_id = str(item.get("canonical_task_id", "")).strip() or str(item.get("task_id", "")).strip()
        group_alias = str(item.get("canonical_task_group_alias", "")).strip() or str(item.get("task_group_alias", "")).strip() or "-"
        task_alias = str(item.get("canonical_task_alias", "")).strip() or str(item.get("task_alias", "")).strip() or "-"
        status = str(item.get("status", "unknown")).strip() or "unknown"
        stage = str(item.get("current_stage", "")).strip() or "-"
        progress = str(item.get("progress_state", "")).strip() or "-"
        next_action = str(item.get("next_action", "")).strip() or "-"
        chats = int(conversation_counts.get(canonical_task_id, 0))
        idle = int(item.get("idle_seconds", 0) or 0)
        goal = str(item.get("goal", "")).strip()
        search = _search_blob(group_alias, task_alias, canonical_task_id, status, stage, progress, next_action, goal)
        rendered.append(
            f"""
            <tr data-row="true" data-order="{len(rendered)}" data-search="{_attr(search)}" data-group="{_attr(group_alias)}" data-node="{_attr(task_alias)}" data-task="{_attr(canonical_task_id)}" data-status="{_attr(status)}" data-status-rank="{_status_rank(status)}" data-stage="{_attr(stage)}" data-progress="{_attr(progress)}" data-chats="{chats}" data-idle="{idle}">
              <td><code>{html.escape(group_alias)}</code></td>
              <td><code>{html.escape(task_alias)}</code></td>
              <td>{html.escape(canonical_task_id)}</td>
              <td>{_badge(status, _tone_for_status(status, needs_intervention=bool(item.get("needs_intervention"))))}</td>
              <td>{html.escape(stage)}</td>
              <td>{html.escape(progress)}</td>
              <td>{html.escape(next_action)}</td>
              <td>{chats}</td>
              <td>{idle}</td>
              <td title="{html.escape(goal)}">{html.escape(_clip(goal, 100) or "-")}</td>
            </tr>
            """
        )
    return "".join(rendered)


def _render_waiting_rows(waiting_registry: Dict[str, Any], *, limit: int = 200) -> str:
    items = waiting_registry.get("items", []) or []
    if not items:
        return '<tr><td colspan="6" class="empty-cell">No waiting tasks</td></tr>'
    rows = []
    for item in items[:limit]:
        waiting_external = item.get("waiting_external", {}) or {}
        group_alias = str(item.get("canonical_task_group_alias", "")).strip() or str(item.get("task_group_alias", "")).strip() or "-"
        task_id = str(item.get("canonical_task_id", "") or item.get("task_id", "")).strip()
        stage = str(item.get("current_stage", "")).strip() or "-"
        next_action = str(item.get("next_action", "")).strip() or "-"
        waiting_reason = str(waiting_external.get("reason", "")).strip() or str(waiting_external.get("status", "")).strip() or "-"
        wait_status = str((item.get("run_liveness", {}) or {}).get("wait_status", "")).strip() or "-"
        search = _search_blob(group_alias, task_id, stage, next_action, waiting_reason, wait_status)
        rows.append(
            f"""
            <tr data-row="true" data-order="{len(rows)}" data-search="{_attr(search)}" data-group="{_attr(group_alias)}" data-task="{_attr(task_id)}" data-stage="{_attr(stage)}" data-waiting-reason="{_attr(waiting_reason)}" data-wait-status="{_attr(wait_status)}">
              <td><code>{html.escape(group_alias)}</code></td>
              <td>{html.escape(task_id)}</td>
              <td>{html.escape(stage)}</td>
              <td>{html.escape(next_action)}</td>
              <td>{html.escape(waiting_reason)}</td>
              <td>{html.escape(wait_status)}</td>
            </tr>
            """
        )
    return "".join(rows)


def _render_doctor_rows(doctor_queue: Dict[str, Any], *, limit: int = 500) -> str:
    items = doctor_queue.get("items", []) or []
    if not items:
        return '<tr><td colspan="7" class="empty-cell">No doctor queue items</td></tr>'
    rows = []
    for item in items[:limit]:
        group_alias = str(item.get("canonical_task_group_alias", "")).strip() or str(item.get("task_group_alias", "")).strip() or "-"
        task_id = str(item.get("canonical_task_id", "") or item.get("task_id", "")).strip()
        priority = str(item.get("priority_bucket", "unknown")).strip() or "unknown"
        status = str(item.get("status", "")).strip() or "-"
        stage = str(item.get("current_stage", "")).strip() or "-"
        reason = str(item.get("reason", "")).strip() or "-"
        idle = int(item.get("idle_seconds", 0) or 0)
        search = _search_blob(group_alias, task_id, priority, status, stage, reason)
        rows.append(
            f"""
            <tr data-row="true" data-order="{len(rows)}" data-search="{_attr(search)}" data-group="{_attr(group_alias)}" data-task="{_attr(task_id)}" data-priority="{_attr(priority)}" data-priority-score="{_priority_rank(priority)}" data-status="{_attr(status)}" data-status-rank="{_status_rank(status)}" data-stage="{_attr(stage)}" data-idle="{idle}">
              <td><code>{html.escape(group_alias)}</code></td>
              <td>{html.escape(task_id)}</td>
              <td>{_badge(priority, _tone_for_status(str(item.get("status", "")), needs_intervention=True))}</td>
              <td>{html.escape(status)}</td>
              <td>{html.escape(stage)}</td>
              <td>{html.escape(reason)}</td>
              <td>{idle}</td>
            </tr>
            """
        )
    return "".join(rows)


def _render_runtime_rows(items: List[Dict[str, Any]], *, kind: str, limit: int = 200) -> str:
    if not items:
        return '<tr><td colspan="4" class="empty-cell">No runtime jobs</td></tr>'
    rows = []
    for item in items[:limit]:
        name = str(item.get("name", "")).strip() or str(item.get("label", "")).strip() or "-"
        label = str(item.get("label", "")).strip() or "-"
        trigger = str(item.get("trigger_summary", "")).strip() or "-"
        description = str(item.get("description", "")).strip() or "-"
        program_summary = str(item.get("program_summary", "")).strip() or "-"
        status_text = str(item.get("status_text", "")).strip() or str(item.get("state", "")).strip() or "-"
        state = str(item.get("state", "")).strip() or "-"
        state_family = str(item.get("state_family", "")).strip() or "idle"
        pid = int(item.get("pid", 0) or 0)
        trigger_sort_value = str(item.get("trigger_sort_value", "")).strip() or trigger
        policy_text = "启动时拉起；退出后自动重启" if kind == "continuous" else trigger
        search = _search_blob(name, label, trigger, description, program_summary, status_text, state)
        rows.append(
            f"""
            <tr data-row="true" data-order="{len(rows)}" data-search="{_attr(search)}" data-name="{_attr(name)}" data-label="{_attr(label)}" data-status-family="{_attr(state_family)}" data-running="{1 if item.get('is_running') else 0}" data-trigger="{_attr(trigger_sort_value)}">
              <td>
                <code title="{html.escape(label)}">{html.escape(name)}</code>
                <div class="cell-note">{html.escape(label)}</div>
                <div class="cell-note">{html.escape(program_summary)}</div>
              </td>
              <td>
                {_badge(status_text, _tone_for_runtime_family(state_family))}
                <div class="cell-note">launchctl: {html.escape(state)}{(f" · pid {pid}" if pid > 0 else "")}</div>
              </td>
              <td>{html.escape(policy_text)}</td>
              <td title="{html.escape(description)}">{html.escape(_clip(description, 140))}</td>
            </tr>
            """
        )
    return "".join(rows)


def _render_retention_summary(task_retention: Dict[str, Any], archived_task_registry: Dict[str, Any]) -> str:
    run_at = str(task_retention.get("generated_at", "")).strip() or "-"
    archived_items = list(archived_task_registry.get("items", []) or [])
    archived_total = len(archived_items)
    archived_this_run = int(task_retention.get("archived_total", 0) or 0)
    candidates_total = int(task_retention.get("candidates_total", 0) or 0)
    skipped_total = int(task_retention.get("skipped_total", 0) or 0)
    terminal_idle_hours = round((int(task_retention.get("terminal_idle_seconds", 0) or 0)) / 3600, 1)
    zombie_idle_days = round((int(task_retention.get("zombie_idle_seconds", 0) or 0)) / 86400, 1)
    latest_archive_at = str((archived_items[-1] if archived_items else {}).get("archived_at", "")).strip() or "-"
    return f"""
    <div class="explain-card">
      <div class="explain-title">Task Retention & Memory Distillation</div>
      <p>归档不是直接删除。系统会先把任务谱系蒸馏成摘要，写回 memory writeback、task summary 和 learning 记录，再把原始任务目录和状态快照移到 archive 区。</p>
      <div class="explain-chip-row">
        <span class="explain-chip"><strong>{archived_total}</strong> archived lineages total</span>
        <span class="explain-chip"><strong>{archived_this_run}</strong> archived this run</span>
        <span class="explain-chip"><strong>{candidates_total}</strong> candidates this run</span>
        <span class="explain-chip"><strong>{skipped_total}</strong> skipped this run</span>
        <span class="explain-chip">terminal idle &ge; <strong>{terminal_idle_hours}</strong>h</span>
        <span class="explain-chip">zombie idle &ge; <strong>{zombie_idle_days}</strong>d</span>
        <span class="explain-chip">last retention run: <strong>{html.escape(run_at)}</strong></span>
        <span class="explain-chip">latest archive at: <strong>{html.escape(latest_archive_at)}</strong></span>
      </div>
    </div>
    """


def _render_archive_rows(archived_task_registry: Dict[str, Any], *, limit: int = 200) -> str:
    items = list(archived_task_registry.get("items", []) or [])
    if not items:
        return '<tr><td colspan="6" class="empty-cell">No archived task lineages yet</td></tr>'
    items.sort(
        key=lambda item: (
            str(item.get("archived_at", "")).strip() or "0000-00-00T00:00:00+00:00",
            str(item.get("lineage_root_task_id", "")).strip(),
        ),
        reverse=True,
    )
    rows = []
    for item in items[:limit]:
        root_task_id = str(item.get("lineage_root_task_id", "")).strip() or "-"
        classification = str(item.get("classification", "")).strip() or "-"
        archived_at = str(item.get("archived_at", "")).strip() or "-"
        task_ids = list(item.get("task_ids", []) or [])
        summary = str(item.get("authoritative_summary", "")).strip() or str(item.get("proof_summary", "")).strip() or "-"
        manifest_path = str(item.get("manifest_path", "")).strip() or "-"
        search = _search_blob(root_task_id, classification, archived_at, " ".join(task_ids), summary, manifest_path)
        rows.append(
            f"""
            <tr data-row="true" data-order="{len(rows)}" data-search="{_attr(search)}" data-root="{_attr(root_task_id)}" data-classification="{_attr(classification)}" data-archived-at="{_attr(archived_at)}" data-task-count="{len(task_ids)}">
              <td>{html.escape(archived_at)}</td>
              <td>{html.escape(root_task_id)}</td>
              <td>{_badge(classification, "muted")}</td>
              <td>{len(task_ids)}</td>
              <td title="{html.escape(summary)}">{html.escape(_clip(summary, 120))}</td>
              <td><code>{html.escape(_clip(manifest_path, 64))}</code></td>
            </tr>
            """
        )
    return "".join(rows)


def build_task_dashboard(
    *,
    system_snapshot: Dict[str, Any],
    runtime_jobs_registry: Dict[str, Any],
    task_registry: Dict[str, Any],
    task_alias_registry: Dict[str, Any],
    conversation_registry: Dict[str, Any],
    conversation_focus_registry: Dict[str, Any] | None = None,
    waiting_registry: Dict[str, Any],
    doctor_queue: Dict[str, Any],
    doctor_incident_inbox: Dict[str, Any],
    task_retention: Dict[str, Any],
    archived_task_registry: Dict[str, Any],
) -> str:
    summary = system_snapshot.get("summary", {}) or {}
    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="15">
  <title>JinClaw Task Board</title>
  <style>
    :root {{
      --bg: #f4efe8;
      --paper: #fffdf9;
      --ink: #1d1a17;
      --muted: #6c665f;
      --line: #dfd5c8;
      --ok: #1f7a55;
      --warn: #a86812;
      --danger: #a53d2d;
      --accent: #0f5b80;
      --shadow: 0 12px 32px rgba(42, 32, 20, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
      background:
        radial-gradient(circle at top left, rgba(15, 91, 128, 0.12), transparent 36%),
        radial-gradient(circle at top right, rgba(168, 104, 18, 0.08), transparent 28%),
        linear-gradient(180deg, #faf6f0 0%, var(--bg) 100%);
    }}
    .wrap {{
      max-width: 1480px;
      margin: 0 auto;
      padding: 28px 24px 48px;
    }}
    .hero, .card {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 22px;
      box-shadow: var(--shadow);
    }}
    .hero {{
      padding: 24px 24px 20px;
      margin-bottom: 20px;
    }}
    .eyebrow {{
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: .08em;
      font-size: 12px;
      font-weight: 700;
      margin-bottom: 8px;
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: 38px;
      line-height: 1.05;
    }}
    .sub {{
      margin: 0;
      color: var(--muted);
      line-height: 1.55;
      max-width: 900px;
    }}
    .meta {{
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      margin-top: 14px;
      color: var(--muted);
      font-size: 14px;
    }}
    .usage {{
      margin-top: 16px;
      padding-top: 16px;
      border-top: 1px dashed var(--line);
    }}
    .usage-title {{
      font-size: 13px;
      color: var(--muted);
      margin-bottom: 8px;
      text-transform: uppercase;
      letter-spacing: .05em;
    }}
    .usage-chips {{
      display: grid;
      gap: 8px;
    }}
    .usage-chips code {{
      display: block;
      background: #f5f0e8;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 10px 12px;
      font-size: 13px;
      overflow-wrap: anywhere;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
      margin: 18px 0 20px;
    }}
    .stat {{
      padding: 16px 18px;
    }}
    .stat-label {{
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: .05em;
      font-size: 12px;
      margin-bottom: 10px;
    }}
    .stat-value {{
      font-size: 30px;
      font-weight: 700;
    }}
    .sections {{
      display: grid;
      gap: 18px;
    }}
    .guide-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
      margin-bottom: 18px;
    }}
    .guide-card, .explain-card {{
      background: rgba(255, 253, 249, 0.82);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px 18px;
      box-shadow: var(--shadow);
    }}
    .guide-title, .explain-title {{
      font-size: 14px;
      font-weight: 700;
      margin-bottom: 8px;
    }}
    .guide-card p, .explain-card p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.55;
      font-size: 14px;
    }}
    .explain-chip-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }}
    .explain-chip {{
      background: #f5f0e8;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 8px 12px;
      font-size: 13px;
    }}
    .card {{
      padding: 18px 18px 14px;
    }}
    .table-tools {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: end;
      margin-bottom: 14px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: #f8f4ec;
    }}
    .table-control {{
      display: grid;
      gap: 6px;
      min-width: 170px;
      flex: 0 1 auto;
    }}
    .table-control-search {{
      min-width: 280px;
      flex: 1 1 320px;
    }}
    .table-control span {{
      font-size: 11px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: .05em;
    }}
    .table-control input,
    .table-control select {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--paper);
      color: var(--ink);
      padding: 10px 12px;
      font: inherit;
    }}
    .table-reset {{
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--paper);
      color: var(--ink);
      padding: 10px 14px;
      font: inherit;
      cursor: pointer;
    }}
    .table-meta {{
      margin-left: auto;
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }}
    .cell-note {{
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
      margin-top: 4px;
      overflow-wrap: anywhere;
    }}
    .section-head {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: end;
      margin-bottom: 14px;
    }}
    .section-head h2 {{
      margin: 0;
      font-size: 24px;
    }}
    .section-head p {{
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 14px;
    }}
    .grid-2 {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      text-align: left;
      padding: 10px 10px;
      border-top: 1px solid var(--line);
      vertical-align: top;
    }}
    th {{
      font-size: 12px;
      letter-spacing: .05em;
      text-transform: uppercase;
      color: var(--muted);
      border-top: 0;
      padding-top: 0;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 4px 9px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid currentColor;
      background: rgba(255,255,255,0.7);
    }}
    .badge-ok {{ color: var(--ok); }}
    .badge-warn {{ color: var(--warn); }}
    .badge-danger {{ color: var(--danger); }}
    .badge-muted {{ color: var(--muted); }}
    .empty-cell {{
      color: var(--muted);
      text-align: center;
      padding: 18px 10px;
    }}
    @media (max-width: 1100px) {{
      .grid-2 {{
        grid-template-columns: 1fr;
      }}
    }}
    @media (max-width: 760px) {{
      .wrap {{
        padding: 18px 14px 30px;
      }}
      h1 {{
        font-size: 30px;
      }}
      .table-control-search,
      .table-control,
      .table-meta {{
        min-width: 100%;
        width: 100%;
      }}
      .table-meta {{
        margin-left: 0;
      }}
      table {{
        display: block;
        overflow-x: auto;
      }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div class="eyebrow">JinClaw Control Plane</div>
      <h1>Task Board</h1>
      <p class="sub">先看每个会话当前聚焦的是哪个任务，再决定跟系统聊哪条链。这样可以把“任务进度”和“当前对话上下文”放到同一个面板里，减少驴唇不对马嘴的情况。</p>
      <div class="meta">
        <span>Generated: {html.escape(str(system_snapshot.get("generated_at", "")))}</span>
        <span>Conversation bindings: {int(summary.get("conversation_bindings_total", 0) or 0)}</span>
        <span>Tracked tasks: {int(summary.get("tasks_total", 0) or 0)}</span>
        <span>Task groups: {int(summary.get("task_groups_total", 0) or 0)}</span>
        <span>Blocked: {int(summary.get("blocked_total", 0) or 0)}</span>
        <span>Doctor queue: {int(summary.get("doctor_queue_total", 0) or 0)}</span>
        <span>AI incidents: {int(summary.get("doctor_active_incident_total", 0) or 0)}</span>
        <span>AI takeovers: {int(summary.get("doctor_ai_takeover_total", 0) or 0)}</span>
        <span>Archived lineages: {int(summary.get("archived_task_lineages_total", 0) or 0)}</span>
        <span>Scheduled jobs: {int(summary.get("scheduled_jobs_running_total", 0) or 0)}/{int(summary.get("scheduled_jobs_total", 0) or 0)}</span>
        <span>Continuous services: {int(summary.get("continuous_jobs_running_total", 0) or 0)}/{int(summary.get("continuous_jobs_total", 0) or 0)}</span>
      </div>
      <div class="usage">
        <div class="usage-title">How To Tell The System Which Task You Mean</div>
        {_render_usage_examples()}
      </div>
    </section>

    <section class="card">
      <div class="section-head">
        <div>
          <h2>AI Incident Inbox</h2>
          <p>把 doctor 刚发现的 <code>process_incidents</code>、<code>task_incidents</code> 和最近完成验收的 <code>resolutions</code> 直接抬到顶部。系统出异常时先看这里。</p>
        </div>
      </div>
      <section class="stats">
        <div class="card stat"><div class="stat-label">Active Incidents</div><div class="stat-value">{int((doctor_incident_inbox.get("summary", {}) or {}).get("active_total", 0) or 0)}</div></div>
        <div class="card stat"><div class="stat-label">Process Incidents</div><div class="stat-value">{int((doctor_incident_inbox.get("summary", {}) or {}).get("process_total", 0) or 0)}</div></div>
        <div class="card stat"><div class="stat-label">Task Incidents</div><div class="stat-value">{int((doctor_incident_inbox.get("summary", {}) or {}).get("task_total", 0) or 0)}</div></div>
        <div class="card stat"><div class="stat-label">AI Takeovers</div><div class="stat-value">{int((doctor_incident_inbox.get("summary", {}) or {}).get("with_ai_takeover_total", 0) or 0)}</div></div>
        <div class="card stat"><div class="stat-label">Recent Resolutions</div><div class="stat-value">{int((doctor_incident_inbox.get("summary", {}) or {}).get("resolutions_total", 0) or 0)}</div></div>
      </section>
      <div class="grid-2">
        <section>
          <div class="section-head">
            <div>
              <h2>Active AI Incidents</h2>
              <p>看 doctor 发现了什么、是否已经派给 AI，以及 AI 现在推进到哪一步。</p>
            </div>
          </div>
          {_render_table_controls(
            "ai-incident-inbox",
            placeholder="搜索 scope、subject、reason、AI watch task",
            filter_key="scope",
            filter_label="Scope",
            filter_options=[("Process", "Process"), ("Task", "Task")],
            sort_options=[
              ("order:asc", "Default"),
              ("severity:asc", "Severity"),
              ("scope:asc", "Scope"),
              ("subject:asc", "Subject"),
              ("generated:asc", "Observed At"),
            ],
          )}
          <table data-sort-table="ai-incident-inbox">
            <thead>
              <tr>
                <th>Scope</th>
                <th>Subject</th>
                <th>Severity</th>
                <th>Incident Status</th>
                <th>Reason</th>
                <th>AI Watch</th>
                <th>AI State</th>
              </tr>
            </thead>
            <tbody>
              {_render_incident_rows(doctor_incident_inbox)}
            </tbody>
          </table>
        </section>
        <section>
          <div class="section-head">
            <div>
              <h2>Recent Resolutions</h2>
              <p>问题解除后，doctor 验收通过并写回的 resolution 结果和 evolution 入口。</p>
            </div>
          </div>
          {_render_table_controls(
            "doctor-resolutions",
            placeholder="搜索 subject、reason、rule、watch task",
            filter_key="scope",
            filter_label="Scope",
            filter_options=[("Process", "Process"), ("Task", "Task")],
            sort_options=[
              ("written-at:desc", "Newest"),
              ("written-at:asc", "Oldest"),
              ("scope:asc", "Scope"),
              ("subject:asc", "Subject"),
            ],
            default_sort="written-at:desc",
          )}
          <table data-sort-table="doctor-resolutions">
            <thead>
              <tr>
                <th>Written At</th>
                <th>Scope</th>
                <th>Subject</th>
                <th>Resolution</th>
                <th>Reusable Rule</th>
                <th>Evolution</th>
              </tr>
            </thead>
            <tbody>
              {_render_resolution_rows(doctor_incident_inbox)}
            </tbody>
          </table>
        </section>
      </div>
    </section>

    <section class="card">
      <div class="section-head">
        <div>
          <h2>Scheduler &amp; Services</h2>
          <p>这里展示这台机器上实际安装的 openclaw `launchd` 任务。左边是按时间触发的定时任务，右边是需要尽量持续在线的常驻服务。</p>
        </div>
      </div>
      <section class="stats">
        <div class="card stat"><div class="stat-label">Scheduled Jobs Running</div><div class="stat-value">{int(summary.get("scheduled_jobs_running_total", 0) or 0)}/{int(summary.get("scheduled_jobs_total", 0) or 0)}</div></div>
        <div class="card stat"><div class="stat-label">Continuous Services Running</div><div class="stat-value">{int(summary.get("continuous_jobs_running_total", 0) or 0)}/{int(summary.get("continuous_jobs_total", 0) or 0)}</div></div>
        <div class="card stat"><div class="stat-label">Current Running Scheduled</div><div class="stat-value">{int(summary.get("scheduled_jobs_running_total", 0) or 0)}</div></div>
        <div class="card stat"><div class="stat-label">Current Running Continuous</div><div class="stat-value">{int(summary.get("continuous_jobs_running_total", 0) or 0)}</div></div>
      </section>
      <div class="grid-2">
        <section>
          <div class="section-head">
            <div>
              <h2>Scheduled Jobs</h2>
              <p>带触发规则的周期任务。正在运行的任务会排在最前面。</p>
            </div>
          </div>
          {_render_table_controls(
            "scheduled-jobs",
            placeholder="搜索任务名、触发规则、用途",
            filter_key="status-family",
            filter_label="Runtime",
            filter_options=[("running", "Running"), ("idle", "Idle"), ("attention", "Attention"), ("not_loaded", "Not Loaded")],
            sort_options=[
              ("running:desc", "Running Now"),
              ("trigger:asc", "Trigger"),
              ("name:asc", "Name"),
              ("status-family:asc", "Runtime"),
            ],
            default_sort="running:desc",
          )}
          <table data-sort-table="scheduled-jobs">
            <thead>
              <tr>
                <th>Job</th>
                <th>Status</th>
                <th>Trigger</th>
                <th>What It Does</th>
              </tr>
            </thead>
            <tbody>
              {_render_runtime_rows(runtime_jobs_registry.get("scheduled_items", []) or [], kind="scheduled")}
            </tbody>
          </table>
        </section>
        <section>
          <div class="section-head">
            <div>
              <h2>Continuous Services</h2>
              <p>常驻型服务。理想状态下应该持续在线，掉线后由 KeepAlive 拉起。</p>
            </div>
          </div>
          {_render_table_controls(
            "continuous-services",
            placeholder="搜索服务名、状态、用途",
            filter_key="status-family",
            filter_label="Runtime",
            filter_options=[("running", "Running"), ("attention", "Attention"), ("not_loaded", "Not Loaded")],
            sort_options=[
              ("running:desc", "Running Now"),
              ("name:asc", "Name"),
              ("status-family:asc", "Runtime"),
            ],
            default_sort="running:desc",
          )}
          <table data-sort-table="continuous-services">
            <thead>
              <tr>
                <th>Service</th>
                <th>Status</th>
                <th>Restart Policy</th>
                <th>What It Does</th>
              </tr>
            </thead>
            <tbody>
              {_render_runtime_rows(runtime_jobs_registry.get("continuous_items", []) or [], kind="continuous")}
            </tbody>
          </table>
        </section>
      </div>
    </section>

    {_render_module_guide()}
    {_render_blocked_summary(summary)}
    {_render_retention_summary(task_retention, archived_task_registry)}

    <section class="stats">
      <div class="card stat"><div class="stat-label">Running Processes</div><div class="stat-value">{int(summary.get("processes_running", 0) or 0)}/{int(summary.get("processes_total", 0) or 0)}</div></div>
      <div class="card stat"><div class="stat-label">Waiting Tasks</div><div class="stat-value">{int(summary.get("waiting_total", 0) or 0)}</div></div>
      <div class="card stat"><div class="stat-label">Blocked By Crawler Remediation</div><div class="stat-value">{int(summary.get("blocked_project_crawler_remediation_total", 0) or 0)}</div></div>
      <div class="card stat"><div class="stat-label">Targeted Fix Blockers</div><div class="stat-value">{int(summary.get("blocked_targeted_fix_total", 0) or 0)}</div></div>
      <div class="card stat"><div class="stat-label">Archived Lineages</div><div class="stat-value">{int(summary.get("archived_task_lineages_total", 0) or 0)}</div></div>
    </section>

    <div class="sections">
      <section class="card">
        <div class="section-head">
          <div>
            <h2>Archive &amp; Memory</h2>
            <p>最近被蒸馏并归档的任务谱系。需要复盘旧任务时先看这里，而不是回到 active 任务目录里找。</p>
          </div>
        </div>
        {_render_table_controls(
          "archive-memory",
          placeholder="搜索 root task、分类、摘要、manifest",
          filter_key="classification",
          filter_label="Class",
          filter_options=[("terminal", "Terminal"), ("approved_zombie", "Approved Zombie"), ("superseded_zombie", "Superseded Zombie"), ("ephemeral_zombie", "Ephemeral Zombie")],
          sort_options=[
            ("archived-at:desc", "Newest"),
            ("archived-at:asc", "Oldest"),
            ("root:asc", "Root Task"),
            ("classification:asc", "Classification"),
            ("task-count:desc", "Task Count"),
          ],
          default_sort="archived-at:desc",
        )}
        <table data-sort-table="archive-memory">
          <thead>
            <tr>
              <th>Archived At</th>
              <th>Root Task</th>
              <th>Class</th>
              <th>Tasks</th>
              <th>Distilled Summary</th>
              <th>Manifest</th>
            </tr>
          </thead>
          <tbody>
            {_render_archive_rows(archived_task_registry)}
          </tbody>
        </table>
      </section>

      <section class="card">
        <div class="section-head">
          <div>
            <h2>Task Directory</h2>
            <p>按任务组展示 root 任务、当前节点和任务用途。找“这个任务具体做什么”时先看这里。</p>
          </div>
        </div>
        {_render_table_controls(
          "task-directory",
          placeholder="搜索任务组、root task、当前节点、用途",
          filter_key="status",
          filter_label="Status",
          filter_options=[("blocked", "Blocked"), ("planning", "Planning"), ("running", "Running"), ("completed", "Completed"), ("failed", "Failed")],
          sort_options=[
            ("order:asc", "Default"),
            ("group:asc", "Group"),
            ("root:asc", "Root Task"),
            ("status-rank:asc", "Status"),
            ("stage:asc", "Stage"),
          ],
        )}
        <table data-sort-table="task-directory">
          <thead>
            <tr>
              <th>Group</th>
              <th>Root Task</th>
              <th>Current Node</th>
              <th>Status</th>
              <th>Stage</th>
              <th>What This Task Does</th>
            </tr>
          </thead>
          <tbody>
            {_render_group_rows(task_alias_registry)}
          </tbody>
        </table>
      </section>

      <section class="card">
        <div class="section-head">
          <div>
            <h2>Conversation Focus</h2>
            <p>每个聊天入口现在绑着哪个任务，以及可直接复制的任务指令格式。</p>
          </div>
        </div>
        {_render_table_controls(
          "conversation-focus",
          placeholder="搜索会话名、任务号、目标、命令",
          filter_key="status",
          filter_label="Status",
          filter_options=[("blocked", "Blocked"), ("planning", "Planning"), ("running", "Running"), ("waiting_external", "Waiting"), ("completed", "Completed"), ("failed", "Failed")],
          sort_options=[
            ("order:asc", "Default"),
            ("conversation:asc", "Conversation"),
            ("group:asc", "Group"),
            ("status-rank:asc", "Status"),
            ("stage:asc", "Stage"),
          ],
        )}
        <table data-sort-table="conversation-focus">
          <thead>
            <tr>
              <th>Conversation</th>
              <th>Alias</th>
              <th>Focused Task</th>
              <th>Status</th>
              <th>Stage</th>
              <th>Next Action</th>
              <th>Last Goal</th>
              <th>Command</th>
            </tr>
          </thead>
          <tbody>
            {_render_focus_rows(conversation_registry.get("items", []) or [])}
          </tbody>
        </table>
      </section>

      <section class="card">
        <div class="section-head">
          <div>
            <h2>Canonical Tasks</h2>
            <p>按 canonical task 聚合后的主任务视图，避免一长串 follow-up 把面板刷乱。</p>
          </div>
        </div>
        {_render_table_controls(
          "canonical-tasks",
          placeholder="搜索任务号、用途、阶段、下一步",
          filter_key="status",
          filter_label="Status",
          filter_options=[("blocked", "Blocked"), ("planning", "Planning"), ("running", "Running"), ("waiting_external", "Waiting"), ("completed", "Completed"), ("failed", "Failed")],
          sort_options=[
            ("order:asc", "Default"),
            ("group:asc", "Group"),
            ("status-rank:asc", "Status"),
            ("stage:asc", "Stage"),
            ("chats:desc", "Chats"),
            ("idle:desc", "Idle Sec"),
          ],
        )}
        <table data-sort-table="canonical-tasks">
          <thead>
            <tr>
              <th>Group</th>
              <th>Node</th>
              <th>Task</th>
              <th>Status</th>
              <th>Stage</th>
              <th>Progress</th>
              <th>Next Action</th>
              <th>Chats</th>
              <th>Idle Sec</th>
              <th>What This Task Does</th>
            </tr>
          </thead>
          <tbody>
            {_render_task_rows(task_registry, conversation_registry)}
          </tbody>
        </table>
      </section>

      <div class="grid-2">
        <section class="card">
          <div class="section-head">
            <div>
              <h2>Waiting</h2>
              <p>当前在等外部条件、审批、回执或运行时信号的任务。</p>
            </div>
          </div>
          {_render_table_controls(
            "waiting",
            placeholder="搜索任务号、等待原因、wait 状态",
            filter_key="stage",
            filter_label="Stage",
            filter_options=[("understand", "Understand"), ("plan", "Plan"), ("execute", "Execute"), ("verify", "Verify"), ("learn", "Learn"), ("-", "None")],
            sort_options=[
              ("order:asc", "Default"),
              ("group:asc", "Group"),
              ("task:asc", "Task"),
              ("stage:asc", "Stage"),
              ("waiting-reason:asc", "Waiting Reason"),
            ],
          )}
          <table data-sort-table="waiting">
            <thead>
              <tr>
                <th>Group</th>
                <th>Task</th>
                <th>Stage</th>
                <th>Next Action</th>
                <th>Waiting Reason</th>
                <th>Wait Status</th>
              </tr>
            </thead>
            <tbody>
              {_render_waiting_rows(waiting_registry)}
            </tbody>
          </table>
        </section>

        <section class="card">
          <div class="section-head">
            <div>
              <h2>Needs Attention</h2>
              <p>医生队列里优先级最高的任务，适合先处理这里再扩新任务。</p>
            </div>
          </div>
          {_render_table_controls(
            "doctor-queue",
            placeholder="搜索任务号、原因、优先级",
            filter_key="priority",
            filter_label="Priority",
            filter_options=[("critical", "Critical"), ("high", "High"), ("medium", "Medium"), ("low", "Low")],
            sort_options=[
              ("order:asc", "Default"),
              ("priority-score:desc", "Priority"),
              ("idle:desc", "Idle Sec"),
              ("task:asc", "Task"),
              ("group:asc", "Group"),
            ],
            default_sort="priority-score:desc",
          )}
          <table data-sort-table="doctor-queue">
            <thead>
              <tr>
                <th>Group</th>
                <th>Task</th>
                <th>Priority</th>
                <th>Status</th>
                <th>Stage</th>
                <th>Reason</th>
                <th>Idle Sec</th>
              </tr>
            </thead>
            <tbody>
              {_render_doctor_rows(doctor_queue)}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  </div>
  <script>
    (() => {{
      const storagePrefix = "jinclaw-task-board:";
      const tableIds = Array.from(document.querySelectorAll("[data-sort-table]")).map((node) => node.getAttribute("data-sort-table"));

      function stateKey(tableId) {{
        return `${{storagePrefix}}${{tableId}}`;
      }}

      function compareValues(left, right, numeric = false) {{
        if (numeric) {{
          return Number(left || 0) - Number(right || 0);
        }}
        return String(left || "").localeCompare(String(right || ""), "zh-CN", {{ numeric: true, sensitivity: "base" }});
      }}

      function applyTable(tableId) {{
        const table = document.querySelector(`[data-sort-table="${{tableId}}"]`);
        const tbody = table?.querySelector("tbody");
        if (!table || !tbody) {{
          return;
        }}
        const rows = Array.from(tbody.querySelectorAll('tr[data-row="true"]'));
        const searchInput = document.querySelector(`[data-table-search="${{tableId}}"]`);
        const filterSelect = document.querySelector(`[data-table-filter="${{tableId}}"]`);
        const sortSelect = document.querySelector(`[data-table-sort="${{tableId}}"]`);
        const resetButton = document.querySelector(`[data-table-reset="${{tableId}}"]`);
        const metaNode = document.querySelector(`[data-table-meta="${{tableId}}"]`);

        try {{
          const saved = JSON.parse(localStorage.getItem(stateKey(tableId)) || "{{}}");
          if (searchInput && typeof saved.search === "string") {{
            searchInput.value = saved.search;
          }}
          if (filterSelect && typeof saved.filter === "string") {{
            filterSelect.value = saved.filter;
          }}
          if (sortSelect && typeof saved.sort === "string") {{
            sortSelect.value = saved.sort;
          }}
        }} catch (_err) {{
        }}

        function saveState() {{
          try {{
            localStorage.setItem(stateKey(tableId), JSON.stringify({{
              search: searchInput?.value || "",
              filter: filterSelect?.value || "",
              sort: sortSelect?.value || sortSelect?.dataset.defaultSort || "order:asc",
            }}));
          }} catch (_err) {{
          }}
        }}

        function apply() {{
          const search = String(searchInput?.value || "").trim().toLowerCase();
          const filterValue = String(filterSelect?.value || "");
          const filterKey = String(filterSelect?.dataset.filterKey || "");
          const sortValue = String(sortSelect?.value || sortSelect?.dataset.defaultSort || "order:asc");
          const [sortKey, sortDirection = "asc"] = sortValue.split(":");
          const numericSort = new Set(["order", "status-rank", "priority-score", "idle", "chats", "running"]).has(sortKey);

          const visible = [];
          const hidden = [];
          for (const row of rows) {{
            const haystack = String(row.getAttribute("data-search") || "").toLowerCase();
            const matchesSearch = !search || haystack.includes(search);
            const matchesFilter = !filterKey || !filterValue || String(row.getAttribute(`data-${{filterKey}}`) || "") === filterValue;
            row.hidden = !(matchesSearch && matchesFilter);
            (row.hidden ? hidden : visible).push(row);
          }}

          visible.sort((left, right) => {{
            const leftValue = left.getAttribute(`data-${{sortKey}}`) || "";
            const rightValue = right.getAttribute(`data-${{sortKey}}`) || "";
            const result = compareValues(leftValue, rightValue, numericSort);
            if (result !== 0) {{
              return sortDirection === "desc" ? -result : result;
            }}
            return compareValues(left.getAttribute("data-order") || 0, right.getAttribute("data-order") || 0, true);
          }});

          for (const row of [...visible, ...hidden]) {{
            tbody.appendChild(row);
          }}
          if (metaNode) {{
            metaNode.textContent = `${{visible.length}} / ${{rows.length}} visible`;
          }}
          saveState();
        }}

        for (const node of [searchInput, filterSelect, sortSelect]) {{
          if (!node) {{
            continue;
          }}
          node.addEventListener("input", apply);
          node.addEventListener("change", apply);
        }}

        if (resetButton) {{
          resetButton.addEventListener("click", () => {{
            if (searchInput) {{
              searchInput.value = "";
            }}
            if (filterSelect) {{
              filterSelect.value = "";
            }}
            if (sortSelect) {{
              sortSelect.value = sortSelect.dataset.defaultSort || "order:asc";
            }}
            apply();
          }});
        }}

        apply();
      }}

      for (const tableId of tableIds) {{
        applyTable(tableId);
      }}
    }})();
  </script>
</body>
</html>
"""
    TASK_BOARD_DASHBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    TASK_BOARD_DASHBOARD_PATH.write_text(html_text, encoding="utf-8")
    return str(TASK_BOARD_DASHBOARD_PATH)
