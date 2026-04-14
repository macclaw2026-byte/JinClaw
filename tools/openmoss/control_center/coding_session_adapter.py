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
- 文件路径：`tools/openmoss/control_center/coding_session_adapter.py`
- 文件作用：把 control center 中的 coding_methodology 元数据，装配成可供 ACP/coding session 使用的标准化派发载荷。
- 设计边界：这是 JinClaw-owned adapter/spec，不伪装成已经存在的运行时派发器；它负责稳定 prompt 组装和 payload 结构，供后续真实 spawn 层调用。
"""
from __future__ import annotations

import json
from typing import Dict, Any


def _coding_methodology_from_contract(contract: Dict[str, Any]) -> Dict[str, Any]:
    metadata = contract.get('metadata', {}) or {}
    control_center = metadata.get('control_center', {}) or {}
    methodology = control_center.get('coding_methodology', {}) or {}
    if methodology:
        return methodology
    return {
        'enabled': False,
        'methodology': 'jinclaw-native',
        'lifecycle': [],
        'prompt_path': '',
        'prompt_text': '',
    }


def _control_center_from_contract(contract: Dict[str, Any]) -> Dict[str, Any]:
    metadata = contract.get('metadata', {}) or {}
    return metadata.get('control_center', {}) or {}


def _base_task_prompt(contract: Dict[str, Any], stage_context: Dict[str, Any] | None = None) -> str:
    stage_context = stage_context or {}
    control_center = _control_center_from_contract(contract)
    goal = str(contract.get('user_goal', '') or '')
    done_definition = str(contract.get('done_definition', '') or '')
    stage_name = str(stage_context.get('stage_name', '') or '')
    stage_goal = str(stage_context.get('stage_goal', '') or '')
    selected_plan = stage_context.get('selected_plan', {}) or {}
    summary = str(selected_plan.get('summary', '') or '')
    governance = stage_context.get('governance_contract', {}) or control_center.get('governance', {}) or {}
    plan_reviews = stage_context.get('plan_reviews', {}) or control_center.get('plan_reviews', {}) or {}
    operating_discipline = stage_context.get('operating_discipline', {}) or control_center.get('operating_discipline', {}) or {}
    protocol_pack = stage_context.get('protocol_pack', {}) or control_center.get('protocol_pack', {}) or {}
    skill_guidance = stage_context.get('skill_guidance', {}) or control_center.get('skill_guidance', {}) or {}
    knowledge_basis = stage_context.get('knowledge_basis', {}) or control_center.get('knowledge_basis', {}) or {}
    readiness_dashboard = stage_context.get('readiness_dashboard', {}) or control_center.get('readiness_dashboard', {}) or {}
    acquisition_hand = stage_context.get('acquisition_hand', {}) or control_center.get('acquisition_hand', {}) or {}
    response_handoff = stage_context.get('response_handoff', {}) or {}
    verification_guidance = stage_context.get('verification_guidance', {}) or {}
    must_fix = plan_reviews.get('must_fix_before_execute', []) or []
    pending_direction = plan_reviews.get('pending_direction_confirmations', []) or []
    pieces = [
        'JinClaw coding execution request',
        f'Goal: {goal}',
        f'Done definition: {done_definition}',
    ]
    if stage_name:
        pieces.append(f'Current stage: {stage_name}')
    if stage_goal:
        pieces.append(f'Stage goal: {stage_goal}')
    if summary:
        pieces.append(f'Selected plan summary: {summary}')
    if governance:
        pieces.append(f"Governance tier: {governance.get('tier', 'standard')}")
    if protocol_pack:
        pieces.append(f"Protocol pack: {protocol_pack.get('pack_id', '')}")
    if skill_guidance.get('enabled'):
        skill_summary = {
            'matched_skill_names': skill_guidance.get('matched_skill_names', []),
            'runtime_prompt_lines': (skill_guidance.get('runtime_prompt_lines', []) or [])[:4],
        }
        pieces.append(f"Skill guidance: {json.dumps(skill_summary, ensure_ascii=False)}")
    if must_fix:
        pieces.append(f'Must-fix before execute: {json.dumps(must_fix, ensure_ascii=False)}')
    if pending_direction:
        pieces.append(f'Pending direction confirmations: {json.dumps(pending_direction, ensure_ascii=False)}')
    enabled_rules = (operating_discipline.get('enabled_rule_keys', []) or [])[:8]
    if enabled_rules:
        pieces.append(f'Operating discipline: {json.dumps(enabled_rules, ensure_ascii=False)}')
    if knowledge_basis:
        pieces.append(f"Knowledge basis: {json.dumps({'recommended_basis': knowledge_basis.get('recommended_basis', ''), 'known_uncertainties': knowledge_basis.get('known_uncertainties', [])}, ensure_ascii=False)}")
    if readiness_dashboard:
        pieces.append(f"Readiness dashboard: {json.dumps({'plan_readiness': readiness_dashboard.get('plan_readiness', {}), 'execute_readiness': readiness_dashboard.get('execute_readiness', {}), 'pending_decisions': readiness_dashboard.get('pending_decisions', [])}, ensure_ascii=False)}")
    if acquisition_hand:
        acquisition_summary = {
            'enabled': acquisition_hand.get('enabled', False),
            'mode': (acquisition_hand.get('execution_strategy', {}) or {}).get('mode', ''),
            'primary_route': ((acquisition_hand.get('summary', {}) or {}).get('primary_route', {})),
            'validation_routes': ((acquisition_hand.get('summary', {}) or {}).get('validation_routes', [])),
        }
        pieces.append(f"Acquisition hand: {json.dumps(acquisition_summary, ensure_ascii=False)}")
    if response_handoff:
        response_summary = {
            'status': response_handoff.get('status', ''),
            'response_mode': response_handoff.get('response_mode', ''),
            'governance_mode': response_handoff.get('governance_mode', ''),
            'requires_disclosure': response_handoff.get('requires_disclosure', False),
            'requires_user_confirmation': response_handoff.get('requires_user_confirmation', False),
            'required_fields_by_site': response_handoff.get('required_fields_by_site', {}),
            'recommended_next_actions': response_handoff.get('recommended_next_actions', []),
        }
        pieces.append(f"Response handoff: {json.dumps(response_summary, ensure_ascii=False)}")
    if verification_guidance:
        pieces.append(f'Verification guidance: {json.dumps(verification_guidance, ensure_ascii=False)}')
    pieces.append('Return a concise completion report with evidence, unresolved risks, and recommended next step.')
    return '\n'.join(pieces)


def build_coding_session_payload(contract: Dict[str, Any], stage_context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    methodology = _coding_methodology_from_contract(contract)
    control_center = _control_center_from_contract(contract)
    stage_context = stage_context or {}
    governance = stage_context.get('governance_contract', {}) or control_center.get('governance', {}) or {}
    protocol_pack = stage_context.get('protocol_pack', {}) or control_center.get('protocol_pack', {}) or {}
    operating_discipline = stage_context.get('operating_discipline', {}) or control_center.get('operating_discipline', {}) or {}
    acquisition_hand = stage_context.get('acquisition_hand', {}) or control_center.get('acquisition_hand', {}) or {}
    response_handoff = stage_context.get('response_handoff', {}) or {}
    base_prompt = _base_task_prompt(contract, stage_context)
    if methodology.get('enabled') and methodology.get('prompt_text'):
        final_prompt = f"{methodology.get('prompt_text').rstrip()}\n\n{base_prompt}"
    else:
        final_prompt = base_prompt
    return {
        'session_kind': 'coding',
        'methodology': methodology,
        'base_prompt': base_prompt,
        'final_prompt': final_prompt,
        'recommended_runtime': 'acp',
        'recommended_mode': 'session',
        'requires_prompt_injection': bool(methodology.get('enabled')),
        'governance': governance,
        'protocol_pack': protocol_pack,
        'operating_discipline': operating_discipline,
        'skill_guidance': stage_context.get('skill_guidance', {}) or control_center.get('skill_guidance', {}) or {},
        'acquisition_hand': acquisition_hand,
        'response_handoff': response_handoff,
    }
