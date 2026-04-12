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
- 文件路径：`tools/openmoss/control_center/workflow_planner.py`
- 文件作用：负责控制中心中与 `workflow_planner` 相关的编排、分析或决策逻辑。
- 顶层函数：_candidate_plans、_choose_best_plan、build_workflow_blueprint、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from typing import Dict, List


def _candidate_plans(intent: Dict[str, object], capabilities: Dict[str, object]) -> List[Dict[str, object]]:
    """
    中文注解：
    - 功能：实现 `_candidate_plans` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    goal = str(intent.get("goal", ""))
    task_types = intent.get("task_types", [])
    local_tags = set(capabilities.get("capability_tags", []))
    plans: List[Dict[str, object]] = []

    plans.append(
        {
            "plan_id": "local_first",
            "label": "Local-first safe execution",
            "summary": "Use existing local skills, scripts, and tools first; only use public network reads when needed.",
            "fit": "primary",
            "steps": [
                "Analyze request and success criteria",
                "Inventory local skills/scripts/tools",
                "Execute with local capabilities first",
                "Use public external research only if local evidence is insufficient",
                "Verify outcome and record learning",
            ],
            "skills": [name for name in ["self-cognition-orchestrator", "capability-gap-router", "continuous-execution-loop"] if any(skill.get("name") == name for skill in capabilities.get("skills", []))],
            "external_actions": [{"type": "public_read", "reason": "fill knowledge gaps with public sources"}] if intent.get("requires_external_information") else [],
            "confidence": "high" if local_tags else "medium",
        }
    )

    if "web" in task_types:
        plans.append(
            {
                "plan_id": "browser_evidence",
                "label": "Browser-backed evidence collection",
                "summary": "Use guarded browser operations and compliant public research to gather stronger evidence.",
                "fit": "strong" if "browser" in local_tags else "conditional",
                "steps": [
                    "Gather static sources first",
                    "Escalate to guarded browser snapshots if rendering matters",
                    "Persist evidence to data/output",
                    "Analyze and verify findings",
                ],
                "skills": [name for name in ["resilient-external-research", "guarded-agent-browser-ops"] if any(skill.get("name") == name for skill in capabilities.get("skills", []))],
                "external_actions": [{"type": "public_read", "reason": "collect public web evidence"}],
                "confidence": "high" if "browser" in local_tags and "research" in local_tags else "medium",
            }
        )

    if "image" in task_types or "marketplace" in task_types:
        plans.append(
            {
                "plan_id": "local_image_pipeline",
                "label": "Local image generation pipeline",
                "summary": "Build or select a local image workflow, generate a first acceptable scene image, verify quality, then continue into the marketplace upload flow.",
                "fit": "strong" if {"browser", "marketplace"} & local_tags else "conditional",
                "steps": [
                    "Identify the exact image and marketplace acceptance requirements",
                    "Inventory local image-generation tools, scripts, and reusable capability clones",
                    "If the best external technique cannot be safely adopted directly, rebuild the useful capability locally",
                    "Generate the first test image and run a quality gate before any upload attempt",
                    "Resume the seller or draft-product workflow only after the image passes verification",
                ],
                "skills": [
                    name
                    for name in [
                        "self-cognition-orchestrator",
                        "capability-gap-router",
                        "continuous-execution-loop",
                        "guarded-agent-browser-ops",
                    ]
                    if any(skill.get("name") == name for skill in capabilities.get("skills", []))
                ],
                "external_actions": [{"type": "public_read", "reason": "study public-safe image workflow references if the local path is insufficient"}],
                "confidence": "high" if {"browser", "marketplace", "generated-capability"} & local_tags else "medium",
            }
        )

    if intent.get("may_download_artifacts"):
        plans.append(
            {
                "plan_id": "audited_external_extension",
                "label": "Audited external extension",
                "summary": "Search for external tools or dependencies, but only after explicit approval and security review.",
                "fit": "fallback",
                "steps": [
                    "Search public sources for candidate tools or solutions",
                    "Run approval and security review",
                    "Install or import only approved items",
                    "Execute, verify, and record durable guidance",
                ],
                "skills": [name for name in ["capability-gap-router", "resilient-external-research", "skill-security-audit"] if any(skill.get("name") == name for skill in capabilities.get("skills", []))],
                "external_actions": [
                    {"type": "public_read", "reason": "discover public solutions"},
                    {"type": "public_download", "reason": "retrieve a candidate tool or artifact"},
                    {"type": "dependency_install", "reason": "install an approved dependency if required"},
                ],
                "confidence": "medium",
            }
        )

        plans.append(
            {
                "plan_id": "in_house_capability_rebuild",
                "label": "In-house capability rebuild",
                "summary": "Study high-value external approaches, keep the safe parts, and rebuild the useful capability locally instead of trusting the third-party artifact directly.",
                "fit": "strong" if "security" in local_tags or "code" in task_types else "conditional",
                "steps": [
                    "Inspect public documentation or source-level evidence for the external approach",
                    "Extract the useful design or workflow advantages without importing unsafe execution paths",
                    "Build a local equivalent using approved in-house code and tools",
                    "Verify that the local replacement reaches the same outcome safely",
                ],
                "skills": [
                    name
                    for name in [
                        "capability-gap-router",
                        "resilient-external-research",
                        "runtime-evolution-loop",
                        "skill-security-audit",
                    ]
                    if any(skill.get("name") == name for skill in capabilities.get("skills", []))
                ],
                "external_actions": [
                    {"type": "public_read", "reason": "study the useful external technique without adopting it directly"}
                ],
                "confidence": "high" if {"security", "research"} & local_tags else "medium",
            }
        )

    return plans


def _choose_best_plan(plans: List[Dict[str, object]], intent: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `_choose_best_plan` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    goal = str(intent.get("goal", "")).lower()
    if any(token in goal for token in ["install", "download", "dependency", "package"]):
        audited = next((plan for plan in plans if plan.get("plan_id") == "audited_external_extension"), None)
        if audited:
            return audited
    if "image" in intent.get("task_types", []) or "marketplace" in intent.get("task_types", []):
        image_pipeline = next((plan for plan in plans if plan.get("plan_id") == "local_image_pipeline"), None)
        if image_pipeline:
            return image_pipeline
    if intent.get("needs_browser"):
        browser = next((plan for plan in plans if plan.get("plan_id") == "browser_evidence"), None)
        if browser:
            return browser
    rank = {"primary": 0, "strong": 1, "conditional": 2, "fallback": 3}
    return sorted(plans, key=lambda item: (rank.get(str(item.get("fit", "fallback")), 9), str(item.get("plan_id", ""))))[0]


def build_workflow_blueprint(intent: Dict[str, object], capabilities: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `build_workflow_blueprint` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    plans = _candidate_plans(intent, capabilities)
    selected = _choose_best_plan(plans, intent)
    return {
        "intent": intent,
        "capabilities_snapshot": {
            "skill_count": capabilities.get("skill_count", 0),
            "script_count": capabilities.get("script_count", 0),
            "tool_count": capabilities.get("tool_count", 0),
            "capability_tags": capabilities.get("capability_tags", []),
        },
        "candidate_plans": plans,
        "selected_plan": selected,
    }


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Build candidate execution plans from mission intent")
    parser.add_argument("--intent-json", required=True)
    parser.add_argument("--capabilities-json", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            build_workflow_blueprint(json.loads(args.intent_json), json.loads(args.capabilities_json)),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
