#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/autonomy/promotion_engine.py`
- 文件作用：负责把重复错误升级为 durable runtime rule。
- 顶层函数：_read_json、_write_json、_classify_failure、load_promoted_rules、resolve_rule_for_error、promote_recurring_errors。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from pathlib import Path

from learning_engine import get_error_recurrence

LEARNING_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/autonomy/learning")
PROMOTED_RULES = LEARNING_ROOT / "promoted_rules.json"
RECURRENCE = LEARNING_ROOT / "error_recurrence.json"


def _read_json(path: Path, default):
    """
    中文注解：
    - 功能：实现 `_read_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _classify_failure(error_text: str) -> str:
    """
    中文注解：
    - 功能：实现 `_classify_failure` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    error = error_text.lower()
    if "timeout" in error or "temporarily" in error:
        return "transient_error"
    if "permission" in error or "denied" in error:
        return "permission_error"
    if "missing" in error or "not found" in error:
        return "missing_dependency"
    if "auth" in error or "token" in error or "unauthorized" in error:
        return "auth_or_config_error"
    if "captcha" in error or "blocked" in error or "rate limit" in error:
        return "anti_automation_or_rate_limit"
    return "general_failure"


def load_promoted_rules() -> dict:
    """
    中文注解：
    - 功能：实现 `load_promoted_rules` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return _read_json(PROMOTED_RULES, {"rules": []})


def load_doctor_strategy_rules() -> list[dict]:
    """
    中文注解：
    - 功能：读取由医生沉淀出的可复用修复/防漂移策略。
    """
    promoted = load_promoted_rules()
    return [dict(rule) for rule in (promoted.get("rules", []) or []) if str(rule.get("rule_scope", "")).strip() == "doctor_strategy"]


def resolve_doctor_strategy(reason: str) -> dict | None:
    """
    中文注解：
    - 功能：根据医生诊断原因查找已推广的修复策略。
    """
    reason = str(reason or "").strip()
    if not reason:
        return None
    for rule in load_doctor_strategy_rules():
        if str(rule.get("doctor_reason", "")).strip() == reason:
            return rule
    return None


def doctor_strategy_bias(intent: dict, plan: dict) -> dict:
    """
    中文注解：
    - 功能：根据已沉淀的医生策略，为候选 plan 生成偏置分。
    - 设计意图：让系统不仅“记住修法”，还会提前更偏向不易漂移、不易卡壳的路径。
    """
    goal = str((intent or {}).get("goal", "") or "").lower()
    task_types = {str(item).strip().lower() for item in ((intent or {}).get("task_types", []) or []) if str(item).strip()}
    needs_browser = bool((intent or {}).get("needs_browser"))
    requires_external_information = bool((intent or {}).get("requires_external_information"))
    plan_id = str((plan or {}).get("plan_id", "") or "").strip()
    rules = load_doctor_strategy_rules()
    adjustment = 0.0
    rationale: list[str] = []

    is_complex_local_optimization = any(
        token in goal for token in ("optimize", "optimization", "improve", "stabilize", "refactor", "复杂", "优化", "改进", "稳定", "重构")
    ) or "code" in task_types

    for rule in rules:
        doctor_reason = str(rule.get("doctor_reason", "")).strip()
        if doctor_reason == "goal_tokens_have_no_overlap_with_current_execution_signals":
            if is_complex_local_optimization and plan_id in {"local_first", "in_house_capability_rebuild"}:
                adjustment += 2.5
                rationale.append("doctor history favors goal-anchored local plans to reduce drift")
            if is_complex_local_optimization and not needs_browser and plan_id in {"browser_evidence", "audited_external_extension"}:
                adjustment -= 3.0
                rationale.append("doctor history penalizes over-broad external plans on drift-prone optimization tasks")
        elif doctor_reason == "completed_without_postmortem":
            if plan_id in {"local_first", "in_house_capability_rebuild"}:
                adjustment += 1.0
                rationale.append("doctor history favors plans that are easier to close with full verification and postmortem")
        elif doctor_reason in {"idle_without_active_execution", "stale_waiting_external"}:
            if requires_external_information and plan_id in {"local_first", "browser_evidence"}:
                adjustment += 1.0
                rationale.append("doctor history favors observable public-read paths when stale waiting has recurred")
        elif doctor_reason == "awaiting_human_guidance":
            if plan_id in {"local_first", "in_house_capability_rebuild"}:
                adjustment += 1.0
                rationale.append("doctor history favors lower-dependency routes when human guidance is often required")

    return {
        "score_adjustment": round(adjustment, 2),
        "rationale": rationale,
        "matched_rule_count": len(rules),
    }


def promote_doctor_strategy(
    *,
    doctor_reason: str,
    preferred_repair: str,
    preferred_escalation_mode: str,
    prevention_hint: str,
    task_id: str,
    evidence: dict | None = None,
) -> dict:
    """
    中文注解：
    - 功能：把医生成功修复一次复杂问题的经验升级成 durable doctor rule。
    - 设计意图：让以后相同类型的漂移/卡壳/门禁问题更快进入正确修法。
    """
    promoted = _read_json(PROMOTED_RULES, {"rules": []})
    rules = list(promoted.get("rules", []) or [])
    for rule in rules:
        if str(rule.get("rule_scope", "")).strip() == "doctor_strategy" and str(rule.get("doctor_reason", "")).strip() == str(doctor_reason).strip():
            rule["count"] = int(rule.get("count", 1) or 1) + 1
            tasks = list(rule.get("tasks", []) or [])
            if task_id not in tasks:
                tasks.append(task_id)
            rule["tasks"] = tasks
            rule["preferred_repair"] = preferred_repair
            rule["preferred_escalation_mode"] = preferred_escalation_mode
            rule["prevention_hint"] = prevention_hint
            if evidence:
                rule["latest_evidence"] = evidence
            _write_json(PROMOTED_RULES, {"rules": rules})
            return rule
    rule = {
        "rule_scope": "doctor_strategy",
        "doctor_reason": str(doctor_reason).strip(),
        "preferred_repair": str(preferred_repair).strip(),
        "preferred_escalation_mode": str(preferred_escalation_mode).strip() or "continue",
        "prevention_hint": str(prevention_hint).strip(),
        "promotion_type": "durable_doctor_rule",
        "source": "doctor_repair_success",
        "count": 1,
        "tasks": [task_id],
        "latest_evidence": evidence or {},
    }
    rules.append(rule)
    _write_json(PROMOTED_RULES, {"rules": rules})
    return rule


def resolve_rule_for_error(error_text: str) -> dict | None:
    """
    中文注解：
    - 功能：实现 `resolve_rule_for_error` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    recurrence = get_error_recurrence(error_text)
    promoted = load_promoted_rules()
    for rule in promoted.get("rules", []):
        if rule.get("error_key") == recurrence.get("key"):
            if not rule.get("preferred_guard"):
                rule["preferred_guard"] = _classify_failure(error_text)
            return rule
    return None


def promote_recurring_errors(min_count: int = 2) -> dict:
    """
    中文注解：
    - 功能：实现 `promote_recurring_errors` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    recurrence = _read_json(RECURRENCE, {"errors": {}})
    promoted = _read_json(PROMOTED_RULES, {"rules": []})
    existing_keys = {rule["error_key"] for rule in promoted["rules"]}
    added = []
    for key, item in recurrence.get("errors", {}).items():
        if item.get("count", 0) < min_count or key in existing_keys:
            continue
        failure_kind = _classify_failure(key)
        rule = {
            "error_key": key,
            "count": item.get("count", 0),
            "recommended_fix": "install stronger verifier and recovery path",
            "preferred_action": "install_preflight_guard_and_targeted_recovery",
            "preferred_guard": failure_kind,
            "prevention_hint": "add a durable preflight check before re-running the same stage",
            "tasks": item.get("tasks", []),
            "promotion_type": "durable_runtime_rule",
            "source": "error_recurrence",
        }
        promoted["rules"].append(rule)
        added.append(rule)
    _write_json(PROMOTED_RULES, promoted)
    return {"added": added, "total_rules": len(promoted["rules"])}


if __name__ == "__main__":
    print(json.dumps(promote_recurring_errors(), ensure_ascii=False, indent=2))
