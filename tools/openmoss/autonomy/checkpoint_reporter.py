#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path

from task_state import TaskState


def render_checkpoint(state: TaskState) -> str:
    completed = [name for name in state.stage_order if state.stages[name].status == "completed"]
    not_completed = [name for name in state.stage_order if state.stages[name].status != "completed"]
    risks = state.blockers or ["none"]
    return "\n".join(
        [
            f"Current stage: {state.current_stage or 'n/a'}",
            f"Completed: {', '.join(completed) if completed else 'none'}",
            f"Not completed: {', '.join(not_completed) if not_completed else 'none'}",
            f"Risks / issues: {', '.join(risks)}",
            f"Suggested next step: {state.next_action}",
            "Continuation mode: auto-continue",
        ]
    )


def write_checkpoint(path: Path, state: TaskState) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = render_checkpoint(state)
    path.write_text(text + "\n", encoding="utf-8")
    return text
