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
- 文件路径：`tools/openmoss/control_center/acp_dispatch_builder.py`
- 文件作用：基于 coding session adapter 的输出，生成一份可供真实 ACP spawn 层直接消费的标准化 dispatch request。
- 设计边界：这是 JinClaw-owned dispatch contract builder，不声称已经替换或接入 OpenClaw 内部 sessions_spawn 实现。
"""
from __future__ import annotations

from typing import Dict, Any

from coding_session_adapter import build_coding_session_payload


def build_acp_dispatch_request(contract: Dict[str, Any], stage_context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    coding_payload = build_coding_session_payload(contract, stage_context)
    methodology = coding_payload.get('methodology', {}) or {}
    governance = coding_payload.get('governance', {}) or {}
    protocol_pack = coding_payload.get('protocol_pack', {}) or {}
    operating_discipline = coding_payload.get('operating_discipline', {}) or {}
    skill_guidance = coding_payload.get('skill_guidance', {}) or {}
    acquisition_hand = coding_payload.get('acquisition_hand', {}) or {}
    response_handoff = coding_payload.get('response_handoff', {}) or {}
    metadata = contract.get('metadata', {}) or {}
    control_center = metadata.get('control_center', {}) or {}
    return {
        'runtime': 'acp',
        'mode': coding_payload.get('recommended_mode', 'session'),
        'thread': True,
        'session_kind': coding_payload.get('session_kind', 'coding'),
        'prompt': coding_payload.get('final_prompt', ''),
        'prompt_components': {
            'methodology_prompt_included': bool(coding_payload.get('requires_prompt_injection')),
            'base_prompt': coding_payload.get('base_prompt', ''),
            'methodology': methodology,
        },
        'env': {
            'OPENCLAW_SESSION': '1',
            'JINCLAW_CODING_METHODOLOGY': str(methodology.get('methodology', 'jinclaw-native')),
            'JINCLAW_GOVERNANCE_TIER': str(governance.get('tier', 'standard')),
            'JINCLAW_PROTOCOL_PACK': str(protocol_pack.get('pack_id', '')),
            'JINCLAW_ACQUISITION_MODE': str((acquisition_hand.get('execution_strategy', {}) or {}).get('mode', 'disabled')),
            'JINCLAW_RESPONSE_MODE': str(response_handoff.get('response_mode', '')),
        },
        'metadata': {
            'task_goal': contract.get('user_goal', ''),
            'done_definition': contract.get('done_definition', ''),
            'control_center_selected_plan': (control_center.get('selected_plan', {}) or {}).get('plan_id', ''),
            'coding_methodology_enabled': bool(methodology.get('enabled')),
            'coding_lifecycle': methodology.get('lifecycle', []),
            'governance_tier': governance.get('tier', 'standard'),
            'protocol_pack_id': protocol_pack.get('pack_id', ''),
            'operating_discipline_rules': (operating_discipline.get('enabled_rule_keys', []) or [])[:10],
            'skill_guidance_enabled': bool(skill_guidance.get('enabled')),
            'matched_skill_names': skill_guidance.get('matched_skill_names', []),
            'acquisition_enabled': bool(acquisition_hand.get('enabled')),
            'acquisition_primary_route': str(((acquisition_hand.get('summary', {}) or {}).get('primary_route', {}) or {}).get('route_id', '')),
            'response_handoff_status': str(response_handoff.get('status', '')),
            'acquisition_response_mode': str(response_handoff.get('response_mode', '')),
            'acquisition_requires_user_confirmation': bool(response_handoff.get('requires_user_confirmation')),
        },
    }
