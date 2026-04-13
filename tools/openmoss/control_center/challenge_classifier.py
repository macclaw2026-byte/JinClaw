#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
"""
中文说明：
- 文件路径：`tools/openmoss/control_center/challenge_classifier.py`
- 文件作用：负责控制中心中与 `challenge_classifier` 相关的编排、分析或决策逻辑。
- 顶层函数：_write_json、classify_challenge、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from paths import CHALLENGES_ROOT


def _write_json(path: Path, payload: object) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _signal(code: str, category: str, severity: str, meaning: str, recommendation: str, evidence: List[str]) -> Dict[str, Any]:
    """
    中文注解：
    - 功能：构造 challenge signal。
    - 设计意图：把原本模糊的 blocker 文本升级成结构化信号，供 fetch route / acquisition hand / doctor 共用。
    """
    return {
        "code": code,
        "category": category,
        "severity": severity,
        "meaning": meaning,
        "recommendation": recommendation,
        "evidence": [str(item) for item in evidence if str(item).strip()],
    }


def _severity_from_signals(signals: List[Dict[str, Any]]) -> str:
    """
    中文注解：
    - 功能：从多个 challenge signal 归并整体严重度。
    - 设计意图：让下游能快速判断是轻微波动、受限但可切换、还是必须停到人工/审批面。
    """
    if any(str(item.get("severity", "")).strip() == "high" for item in signals):
        return "high"
    if any(str(item.get("severity", "")).strip() == "medium" for item in signals):
        return "medium"
    if any(str(item.get("severity", "")).strip() == "low" for item in signals):
        return "low"
    return "none"


def classify_challenge(task_id: str, blockers: List[str], state: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `classify_challenge` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    text = " | ".join([str(item) for item in blockers]).lower()
    evidence = [str(item).strip() for item in blockers if str(item).strip()]
    challenge_type = "none"
    recommended_route = "continue"
    signals: List[Dict[str, Any]] = []
    safe_next_routes: List[str] = []
    if any(token in text for token in ["captcha", "turnstile", "challenge page", "verify you are human"]):
        challenge_type = "human_verification_required"
        recommended_route = "human_checkpoint"
        signals.append(
            _signal(
                "human_verification_gate",
                "anti_bot",
                "high",
                "目标站点要求人工验证，自动链路不应继续强推。",
                "stop_and_escalate_to_human_checkpoint",
                evidence,
            )
        )
        safe_next_routes = ["human_checkpoint"]
    elif any(token in text for token in ["403", "forbidden", "access denied"]):
        challenge_type = "waf_or_access_block"
        recommended_route = "official_source_or_authorized_session"
        signals.append(
            _signal(
                "waf_or_access_block",
                "access_control",
                "high",
                "站点返回了明确的访问控制阻断信号。",
                "switch_to_official_or_approved_route",
                evidence,
            )
        )
        safe_next_routes = ["official_api", "structured_public_endpoint", "authorized_session", "human_checkpoint"]
    elif any(token in text for token in ["429", "rate limit", "too many requests"]):
        challenge_type = "rate_limit"
        recommended_route = "slow_down_and_switch_to_structured_source"
        signals.append(
            _signal(
                "rate_limit_pressure",
                "traffic_governance",
                "medium",
                "当前路线触发了速率限制，应该降速并切换到更稳的结构化来源。",
                "slow_down_and_switch_routes",
                evidence,
            )
        )
        safe_next_routes = ["official_api", "structured_public_endpoint", "static_fetch"]
    elif any(token in text for token in ["login", "sign in", "authentication", "authorized session"]):
        challenge_type = "authorization_required"
        recommended_route = "authorized_session"
        signals.append(
            _signal(
                "authorization_required",
                "approval",
                "high",
                "当前目标需要登录态或已批准授权态才能继续。",
                "pause_until_authorized_session_is_reviewed",
                evidence,
            )
        )
        safe_next_routes = ["authorized_session", "human_checkpoint"]
    elif any(token in text for token in ["loading", "client rendered", "javascript", "render", "dynamic content"]):
        challenge_type = "rendering_barrier"
        recommended_route = "browser_render"
        signals.append(
            _signal(
                "rendering_barrier",
                "rendering",
                "low",
                "当前页面更像是客户端渲染或强动态内容，需要浏览器证据链。",
                "upgrade_to_browser_render",
                evidence,
            )
        )
        safe_next_routes = ["browser_render", "authorized_session", "human_checkpoint"]
    severity = _severity_from_signals(signals)
    requires_human_checkpoint = bool(challenge_type == "human_verification_required")
    requires_authorized_session_review = bool(challenge_type in {"authorization_required", "waf_or_access_block"})
    payload = {
        "task_id": task_id,
        "challenge_type": challenge_type,
        "recommended_route": recommended_route,
        "blockers": blockers,
        "status": state.get("status", ""),
        "current_stage": state.get("current_stage", ""),
        "severity": severity,
        "signals": signals,
        "safe_next_routes": safe_next_routes,
        "requires_human_checkpoint": requires_human_checkpoint,
        "requires_authorized_session_review": requires_authorized_session_review,
        "anti_bot_posture": {
            "mode": "guarded" if severity in {"medium", "high"} else "normal",
            "guidance": [
                "prefer route switching over forcing the same blocked tactic",
                "never bypass human verification or auth requirements",
                "preserve evidence so the doctor and runtime can explain why the route changed",
            ],
            "avoid_actions": [
                "repeating the same blocked browser tactic",
                "silent escalation into higher-risk routes without review",
            ],
        },
    }
    _write_json(CHALLENGES_ROOT / f"{task_id}.json", payload)
    return payload


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Classify web-access challenges and recommend a compliant route")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--blockers-json", required=True)
    parser.add_argument("--state-json", required=True)
    args = parser.parse_args()
    print(json.dumps(classify_challenge(args.task_id, json.loads(args.blockers_json), json.loads(args.state_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
