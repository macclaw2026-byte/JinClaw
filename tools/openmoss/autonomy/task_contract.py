#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List

WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
LEARNING_ROOT = WORKSPACE_ROOT / "tools/openmoss/runtime/autonomy/learning"
OUTPUT_ROOT = WORKSPACE_ROOT / "output"
DATA_ROOT = WORKSPACE_ROOT / "data"


DEFAULT_STAGE_EXECUTION_POLICIES = {
    "understand": {
        "auto_complete_on_wait_ok": True,
        "required_commands": [],
        "required_paths": [],
        "writable_paths": [],
    },
    "plan": {
        "auto_complete_on_wait_ok": True,
        "required_commands": [],
        "required_paths": [],
        "writable_paths": [],
    },
    "execute": {
        "auto_complete_on_wait_ok": True,
        "required_commands": [],
        "required_paths": [],
        "writable_paths": [],
    },
    "verify": {
        "auto_complete_on_wait_ok": False,
        "required_commands": [],
        "required_paths": [],
        "writable_paths": [],
    },
    "learn": {
        "auto_complete_on_wait_ok": True,
        "required_commands": [],
        "required_paths": [],
        "writable_paths": [],
    },
}


def _merge_unique(values: List[str], extras: List[str]) -> List[str]:
    seen = set()
    merged: List[str] = []
    for value in [*values, *extras]:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        merged.append(item)
    return merged


def infer_stage_execution_policy(goal: str, stage_name: str, allowed_tools: List[str] | None = None) -> Dict[str, Any]:
    normalized_goal = goal.lower()
    allowed = {str(item).strip().lower() for item in (allowed_tools or []) if str(item).strip()}
    base = dict(DEFAULT_STAGE_EXECUTION_POLICIES.get(stage_name, {"auto_complete_on_wait_ok": False}))

    required_commands: List[str] = []
    required_paths: List[str] = []
    writable_paths: List[str] = []

    looks_like_web_task = any(token in normalized_goal for token in ["crawl", "scrape", "fetch", "browser", "amazon", "website", "web"])
    looks_like_code_task = any(token in normalized_goal for token in ["code", "build", "implement", "test", "fix", "debug"])
    looks_like_data_task = any(token in normalized_goal for token in ["data", "analyze", "analysis", "report", "json", "csv"])

    if stage_name in {"understand", "plan"}:
        required_commands = ["rg"]
        required_paths = [str(WORKSPACE_ROOT)]

    if stage_name == "execute":
        required_commands = ["rg"]
        writable_paths = [str(OUTPUT_ROOT)]
        if looks_like_web_task or "browser" in allowed:
            required_paths.append(str(WORKSPACE_ROOT / "tools"))
            writable_paths.extend([str(DATA_ROOT), str(OUTPUT_ROOT)])
        if looks_like_code_task:
            writable_paths.append(str(WORKSPACE_ROOT))
        if looks_like_data_task:
            writable_paths.extend([str(DATA_ROOT), str(OUTPUT_ROOT)])

    if stage_name == "verify":
        required_commands = ["rg"]
        required_paths = [str(WORKSPACE_ROOT)]
        if looks_like_data_task or looks_like_web_task:
            required_paths.extend([str(DATA_ROOT), str(OUTPUT_ROOT)])

    if stage_name == "learn":
        writable_paths = [str(LEARNING_ROOT)]

    base["required_commands"] = _merge_unique(base.get("required_commands", []), required_commands)
    base["required_paths"] = _merge_unique(base.get("required_paths", []), required_paths)
    base["writable_paths"] = _merge_unique(base.get("writable_paths", []), writable_paths)
    return base


def merge_execution_policy(goal: str, stage_name: str, existing: Dict[str, Any] | None = None, allowed_tools: List[str] | None = None) -> Dict[str, Any]:
    inferred = infer_stage_execution_policy(goal, stage_name, allowed_tools=allowed_tools)
    current = dict(existing or {})
    merged = {**inferred, **current}
    merged["required_commands"] = _merge_unique(inferred.get("required_commands", []), current.get("required_commands", []))
    merged["required_paths"] = _merge_unique(inferred.get("required_paths", []), current.get("required_paths", []))
    merged["writable_paths"] = _merge_unique(inferred.get("writable_paths", []), current.get("writable_paths", []))
    return merged


@dataclass
class StageContract:
    name: str
    goal: str
    expected_output: str = ""
    acceptance_check: str = ""
    next_stage_trigger: str = ""
    fallback_rule: str = ""
    primary_monitor: str = ""
    backstop_monitor: str = ""
    miss_detection_signal: str = ""
    verifier: Dict[str, Any] = field(default_factory=dict)
    execution_policy: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskContract:
    task_id: str
    user_goal: str
    done_definition: str
    hard_constraints: List[str] = field(default_factory=list)
    soft_preferences: List[str] = field(default_factory=list)
    allowed_tools: List[str] = field(default_factory=list)
    forbidden_actions: List[str] = field(default_factory=list)
    checkpoint_policy: str = "every-stage"
    retry_policy: str = "recover-then-retry"
    escalation_policy: str = "only-if-truly-blocked"
    continuation_mode: str = "auto-continue"
    stages: List[StageContract] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskContract":
        user_goal = str(data.get("user_goal", ""))
        allowed_tools = [str(item) for item in data.get("allowed_tools", [])]
        stages = []
        for stage in data.get("stages", []):
            payload = dict(stage)
            payload["execution_policy"] = merge_execution_policy(
                user_goal,
                payload.get("name", ""),
                payload.get("execution_policy", {}),
                allowed_tools=allowed_tools,
            )
            stages.append(StageContract(**payload))
        payload = dict(data)
        payload["stages"] = stages
        return cls(**payload)
