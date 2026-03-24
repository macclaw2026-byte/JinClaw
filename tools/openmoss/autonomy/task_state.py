#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


TASK_STATUSES = {
    "created",
    "planning",
    "running",
    "waiting_external",
    "blocked",
    "recovering",
    "verifying",
    "learning",
    "completed",
    "failed",
}

STAGE_STATUSES = {
    "pending",
    "running",
    "completed",
    "blocked",
    "failed",
    "skipped",
}


@dataclass
class StageState:
    name: str
    status: str = "pending"
    attempts: int = 0
    summary: str = ""
    verification_status: str = "not-run"
    blocker: str = ""
    started_at: str = ""
    completed_at: str = ""
    updated_at: str = ""
    evidence_refs: List[str] = field(default_factory=list)
    last_execution_status: str = ""
    subtask_cursor: int = 0
    completed_subtasks: List[str] = field(default_factory=list)


@dataclass
class TaskState:
    task_id: str
    status: str = "created"
    current_stage: str = ""
    attempts: int = 0
    next_action: str = "initialize"
    last_progress_at: str = ""
    last_success_at: str = ""
    last_update_at: str = ""
    blockers: List[str] = field(default_factory=list)
    learning_backlog: List[str] = field(default_factory=list)
    stage_order: List[str] = field(default_factory=list)
    stages: Dict[str, StageState] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["stages"] = {name: asdict(stage) for name, stage in self.stages.items()}
        return payload

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskState":
        payload = dict(data)
        payload["stages"] = {
            name: StageState(**stage_data)
            for name, stage_data in payload.get("stages", {}).items()
        }
        return cls(**payload)

    def first_pending_stage(self) -> Optional[str]:
        for name in self.stage_order:
            stage = self.stages.get(name)
            if stage and stage.status in {"pending", "failed", "blocked"}:
                return name
        return None
