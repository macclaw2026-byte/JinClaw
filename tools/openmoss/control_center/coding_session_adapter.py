#!/usr/bin/env python3

"""
中文说明：
- 文件路径：`tools/openmoss/control_center/coding_session_adapter.py`
- 文件作用：把 control center 中的 coding_methodology 元数据，装配成可供 ACP/coding session 使用的标准化派发载荷。
- 设计边界：这是 JinClaw-owned adapter/spec，不伪装成已经存在的运行时派发器；它负责稳定 prompt 组装和 payload 结构，供后续真实 spawn 层调用。
"""
from __future__ import annotations

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


def _base_task_prompt(contract: Dict[str, Any], stage_context: Dict[str, Any] | None = None) -> str:
    stage_context = stage_context or {}
    goal = str(contract.get('user_goal', '') or '')
    done_definition = str(contract.get('done_definition', '') or '')
    stage_name = str(stage_context.get('stage_name', '') or '')
    stage_goal = str(stage_context.get('stage_goal', '') or '')
    selected_plan = stage_context.get('selected_plan', {}) or {}
    summary = str(selected_plan.get('summary', '') or '')
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
    pieces.append('Return a concise completion report with evidence, unresolved risks, and recommended next step.')
    return '\n'.join(pieces)


def build_coding_session_payload(contract: Dict[str, Any], stage_context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    methodology = _coding_methodology_from_contract(contract)
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
    }
