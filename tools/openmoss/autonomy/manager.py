#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from checkpoint_reporter import render_checkpoint, write_checkpoint
from learning_engine import get_error_recurrence, note_error_occurrence, record_error, record_learning, update_task_summary
from recovery_engine import apply_recovery_action, propose_recovery
from task_contract import StageContract, TaskContract, merge_execution_policy
from task_state import StageState, TaskState
from verifier_registry import run_verifier

CONTROL_CENTER_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/control_center")
if str(CONTROL_CENTER_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER_DIR))

from plan_history import record_plan_outcome


def _plan_bucket(contract: TaskContract) -> tuple[list[str], str]:
    intent = contract.metadata.get("control_center", {}).get("intent", {})
    return [str(item) for item in intent.get("task_types", [])], str(intent.get("risk_level", ""))


RUNTIME_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/autonomy")
TASKS_ROOT = RUNTIME_ROOT / "tasks"
INGRESS_ROOT = RUNTIME_ROOT / "ingress"
LINKS_ROOT = RUNTIME_ROOT / "links"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_args(**kwargs):
    return argparse.Namespace(**kwargs)


def task_dir(task_id: str) -> Path:
    return TASKS_ROOT / task_id


def read_json(path: Path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def append_jsonl(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def ingress_path(source: str) -> Path:
    return INGRESS_ROOT / f"{source}.jsonl"


def link_path(provider: str, conversation_id: str) -> Path:
    safe_provider = provider.replace("/", "-")
    safe_conversation = conversation_id.replace("/", "-")
    return LINKS_ROOT / f"{safe_provider}__{safe_conversation}.json"


def contract_path(task_id: str) -> Path:
    return task_dir(task_id) / "contract.json"


def state_path(task_id: str) -> Path:
    return task_dir(task_id) / "state.json"


def events_path(task_id: str) -> Path:
    return task_dir(task_id) / "events.jsonl"


def checkpoints_dir(task_id: str) -> Path:
    return task_dir(task_id) / "checkpoints"


def _refresh_task_summary(task_id: str, *, state: TaskState | None = None, extra: Dict | None = None) -> Dict:
    current = state or load_state(task_id)
    completed_stages = [name for name in current.stage_order if current.stages.get(name) and current.stages[name].status == "completed"]
    payload = {
        "status": current.status,
        "current_stage": current.current_stage,
        "learning_backlog": current.learning_backlog,
        "completed_stages": completed_stages,
        "last_completed_stage": completed_stages[-1] if completed_stages else "",
    }
    if extra:
        payload.update(extra)
    return update_task_summary(task_id, payload)


def load_contract(task_id: str) -> TaskContract:
    return TaskContract.from_dict(read_json(contract_path(task_id), {}))


def load_state(task_id: str) -> TaskState:
    return TaskState.from_dict(read_json(state_path(task_id), {}))


def save_contract(contract: TaskContract) -> None:
    write_json(contract_path(contract.task_id), contract.to_dict())


def save_state(state: TaskState) -> None:
    write_json(state_path(state.task_id), state.to_dict())


def log_event(task_id: str, event_type: str, **extra) -> None:
    payload = {"at": utc_now_iso(), "type": event_type}
    payload.update(extra)
    append_jsonl(events_path(task_id), payload)


def log_ingress(source: str, payload: Dict) -> None:
    data = {"at": utc_now_iso(), "source": source}
    data.update(payload)
    append_jsonl(ingress_path(source), data)


def write_link(provider: str, conversation_id: str, payload: Dict) -> str:
    path = link_path(provider, conversation_id)
    write_json(path, payload)
    return str(path)


def read_link(provider: str, conversation_id: str) -> Dict:
    return read_json(link_path(provider, conversation_id), {})


def find_link_by_task_id(task_id: str) -> Dict:
    if not LINKS_ROOT.exists():
        return {}
    for path in sorted(LINKS_ROOT.glob("*.json")):
        payload = read_json(path, {})
        if payload.get("task_id") == task_id:
            payload["_path"] = str(path)
            return payload
    return {}


def parse_stage_args(stage_args: List[str]) -> List[StageContract]:
    stages: List[StageContract] = []
    for raw in stage_args:
        name, sep, goal = raw.partition("|")
        if not sep:
            raise ValueError(f"invalid stage format: {raw}")
        stages.append(StageContract(name=name.strip(), goal=goal.strip()))
    return stages


def parse_stage_payloads(stage_payloads: List[Dict]) -> List[StageContract]:
    stages: List[StageContract] = []
    for payload in stage_payloads:
        stages.append(StageContract(**payload))
    return stages


def create_task_from_contract(contract: TaskContract) -> Dict[str, Dict]:
    stages = contract.stages
    state = TaskState(
        task_id=contract.task_id,
        status="planning",
        current_stage=stages[0].name if stages else "",
        next_action=f"start_stage:{stages[0].name}" if stages else "noop",
        last_update_at=utc_now_iso(),
        stage_order=[stage.name for stage in stages],
        stages={stage.name: StageState(name=stage.name, updated_at=utc_now_iso()) for stage in stages},
        metadata={"contract_metadata": contract.metadata},
    )
    save_contract(contract)
    save_state(state)
    _refresh_task_summary(contract.task_id, state=state, extra={"goal": contract.user_goal, "done_definition": contract.done_definition})
    log_event(contract.task_id, "task_created", goal=contract.user_goal, done_definition=contract.done_definition, metadata=contract.metadata)
    return {"contract": contract.to_dict(), "state": state.to_dict()}


def create_task(args: argparse.Namespace) -> int:
    if getattr(args, "stage_json", ""):
        stages = parse_stage_payloads(json.loads(args.stage_json))
    else:
        stages = parse_stage_args(args.stage)
    allowed_tools = args.allowed_tool or []
    for stage in stages:
        stage.execution_policy = merge_execution_policy(
            args.goal,
            stage.name,
            stage.execution_policy,
            allowed_tools=allowed_tools,
        )
    contract = TaskContract(
        task_id=args.task_id,
        user_goal=args.goal,
        done_definition=args.done_definition,
        hard_constraints=args.hard_constraint or [],
        soft_preferences=args.soft_preference or [],
        allowed_tools=allowed_tools,
        forbidden_actions=args.forbidden_action or [],
        stages=stages,
        metadata={
            "created_at": utc_now_iso(),
            **json.loads(getattr(args, "metadata_json", "") or "{}"),
        },
    )
    payload = create_task_from_contract(contract)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def status_task(args: argparse.Namespace) -> int:
    contract = load_contract(args.task_id)
    state = load_state(args.task_id)
    payload = {
        "contract": contract.to_dict(),
        "state": state.to_dict(),
        "checkpoint_preview": render_checkpoint(state),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def list_tasks(args: argparse.Namespace) -> int:
    payload = []
    if not TASKS_ROOT.exists():
        print("[]")
        return 0
    for task_root in sorted(TASKS_ROOT.iterdir()):
        if not task_root.is_dir():
            continue
        state = load_state(task_root.name)
        payload.append(
            {
                "task_id": task_root.name,
                "status": state.status,
                "current_stage": state.current_stage,
                "next_action": state.next_action,
                "last_update_at": state.last_update_at,
            }
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def run_once(args: argparse.Namespace) -> int:
    contract = load_contract(args.task_id)
    state = load_state(args.task_id)
    if state.status in {"completed", "failed"}:
        print(json.dumps({"status": state.status, "message": "task already terminal"}, ensure_ascii=False, indent=2))
        return 0

    stage_name = state.current_stage or state.first_pending_stage()
    if not stage_name:
        state.status = "verifying"
        state.next_action = "verify_done_definition"
        state.last_update_at = utc_now_iso()
        save_state(state)
        log_event(args.task_id, "entered_verifying")
        print(json.dumps({"status": "verifying", "next_action": state.next_action}, ensure_ascii=False, indent=2))
        return 0

    stage = state.stages[stage_name]
    stage.status = "running"
    stage.attempts += 1
    stage.started_at = stage.started_at or utc_now_iso()
    stage.updated_at = utc_now_iso()
    state.status = "running"
    state.current_stage = stage_name
    state.attempts += 1
    state.next_action = f"execute_stage:{stage_name}"
    state.last_progress_at = utc_now_iso()
    state.last_update_at = utc_now_iso()
    save_state(state)
    log_event(args.task_id, "stage_started", stage=stage_name, attempts=stage.attempts)
    print(
        json.dumps(
            {
                "status": "running",
                "current_stage": stage_name,
                "stage_goal": next((s.goal for s in contract.stages if s.name == stage_name), ""),
                "next_action": state.next_action,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def recover_task(args: argparse.Namespace) -> int:
    state = load_state(args.task_id)
    stage_name = args.stage or state.current_stage
    if not stage_name or stage_name not in state.stages:
        raise SystemExit("unknown stage")
    stage = state.stages[stage_name]
    stage.status = "pending"
    stage.blocker = ""
    stage.summary = args.summary
    stage.updated_at = utc_now_iso()
    state.status = "planning"
    state.current_stage = stage_name
    state.blockers = []
    state.next_action = f"start_stage:{stage_name}"
    state.last_update_at = utc_now_iso()
    save_state(state)
    log_event(args.task_id, "stage_recovered", stage=stage_name, summary=args.summary)
    record_learning(args.task_id, f"Recovery applied for {stage_name}: {args.summary}")
    _refresh_task_summary(args.task_id, state=state, extra={"last_recovery": {"stage": stage_name, "summary": args.summary}})
    print(json.dumps({"status": state.status, "next_action": state.next_action}, ensure_ascii=False, indent=2))
    return 0


def apply_recovery(args: argparse.Namespace) -> int:
    state = load_state(args.task_id)
    stage_name = args.stage or state.current_stage
    if not stage_name or stage_name not in state.stages:
        raise SystemExit("unknown stage")
    stage = state.stages[stage_name]
    action = args.action or state.next_action
    result = apply_recovery_action(action, stage.blocker or " ".join(state.blockers))
    stage.updated_at = utc_now_iso()
    state.last_update_at = utc_now_iso()
    if result.get("ok") == "true":
        stage.status = "pending"
        stage.blocker = ""
        state.status = "planning"
        state.blockers = []
        state.next_action = f"start_stage:{stage_name}"
        record_learning(args.task_id, f"Auto-recovery succeeded for {stage_name}: {action}")
    else:
        state.status = "blocked"
        state.next_action = action
        record_error(args.task_id, f"Auto-recovery failed for {stage_name}: {action} -> {result.get('status')}")
    save_state(state)
    _refresh_task_summary(
        args.task_id,
        state=state,
        extra={"last_recovery": {"stage": stage_name, "action": action, "result": result}},
    )
    log_event(args.task_id, "recovery_applied", stage=stage_name, action=action, result=result)
    print(json.dumps({"task_id": args.task_id, "stage": stage_name, "action": action, "result": result, "status": state.status}, ensure_ascii=False, indent=2))
    return 0


def complete_stage(args: argparse.Namespace) -> int:
    contract = load_contract(args.task_id)
    state = load_state(args.task_id)
    stage_name = args.stage or state.current_stage
    if not stage_name or stage_name not in state.stages:
        raise SystemExit("unknown stage")
    stage = state.stages[stage_name]
    stage.status = "completed"
    stage.summary = args.summary
    stage.completed_at = utc_now_iso()
    stage.updated_at = utc_now_iso()
    state.last_success_at = utc_now_iso()
    state.last_update_at = utc_now_iso()
    next_stage = None
    for name in state.stage_order:
        if state.stages[name].status != "completed":
            next_stage = name
            break
    if next_stage is None:
        state.status = "verifying"
        state.current_stage = ""
        state.next_action = "verify_done_definition"
    else:
        state.status = "planning"
        state.current_stage = next_stage
        state.next_action = f"start_stage:{next_stage}"
    save_state(state)
    log_event(args.task_id, "stage_completed", stage=stage_name, summary=args.summary)
    record_learning(args.task_id, f"Stage {stage_name} completed: {args.summary}")
    _refresh_task_summary(args.task_id, state=state, extra={"last_completed_stage": stage_name})
    print(json.dumps({"status": state.status, "next_action": state.next_action}, ensure_ascii=False, indent=2))
    return 0


def complete_stage_internal(task_id: str, stage_name: str, summary: str, evidence_ref: str = "") -> Dict[str, str]:
    state = load_state(task_id)
    if stage_name not in state.stages:
        raise ValueError(f"unknown stage: {stage_name}")
    stage = state.stages[stage_name]
    stage.status = "completed"
    stage.summary = summary
    stage.completed_at = utc_now_iso()
    stage.updated_at = utc_now_iso()
    if evidence_ref:
        stage.evidence_refs.append(evidence_ref)
    state.last_success_at = utc_now_iso()
    state.last_update_at = utc_now_iso()
    next_stage = None
    for name in state.stage_order:
        if state.stages[name].status != "completed":
            next_stage = name
            break
    if next_stage is None:
        state.status = "verifying"
        state.current_stage = ""
        state.next_action = "verify_done_definition"
    else:
        state.status = "planning"
        state.current_stage = next_stage
        state.next_action = f"start_stage:{next_stage}"
    save_state(state)
    log_event(task_id, "stage_completed", stage=stage_name, summary=summary, evidence_ref=evidence_ref)
    record_learning(task_id, f"Stage {stage_name} completed: {summary}")
    if stage_name == "execute":
        contract = load_contract(task_id)
        plan_id = str(contract.metadata.get("control_center", {}).get("selected_plan", {}).get("plan_id", ""))
        if plan_id:
            task_types, risk_level = _plan_bucket(contract)
            record_plan_outcome(plan_id, "success", task_types=task_types, risk_level=risk_level)
    _refresh_task_summary(task_id, state=state, extra={"last_completed_stage": stage_name})
    return {"status": state.status, "next_action": state.next_action}


def advance_execute_subtask(task_id: str, subtask_id: str, summary: str = "") -> Dict[str, object]:
    state = load_state(task_id)
    stage = state.stages.get("execute")
    if not stage:
        raise ValueError("execute stage not found")
    if subtask_id and subtask_id not in stage.completed_subtasks:
        stage.completed_subtasks.append(subtask_id)
    stage.subtask_cursor = len(stage.completed_subtasks)
    stage.updated_at = utc_now_iso()
    if summary:
        stage.summary = summary
    state.last_update_at = utc_now_iso()
    save_state(state)
    log_event(task_id, "execute_subtask_advanced", subtask_id=subtask_id, completed_subtasks=stage.completed_subtasks, subtask_cursor=stage.subtask_cursor)
    return {
        "task_id": task_id,
        "stage": "execute",
        "subtask_id": subtask_id,
        "completed_subtasks": stage.completed_subtasks,
        "subtask_cursor": stage.subtask_cursor,
    }


def fail_stage(args: argparse.Namespace) -> int:
    state = load_state(args.task_id)
    stage_name = args.stage or state.current_stage
    if not stage_name or stage_name not in state.stages:
        raise SystemExit("unknown stage")
    stage = state.stages[stage_name]
    stage.status = "failed"
    stage.blocker = args.error
    stage.updated_at = utc_now_iso()
    state.status = "recovering"
    state.current_stage = stage_name
    state.blockers = [args.error]
    state.learning_backlog = list(dict.fromkeys([*state.learning_backlog, f"prevent_repeat:{stage_name}"]))
    state.last_update_at = utc_now_iso()
    recovery = propose_recovery(args.error, stage.attempts)
    state.next_action = recovery["action"]
    save_state(state)
    recurrence = note_error_occurrence(args.task_id, args.error)
    contract = load_contract(args.task_id)
    plan_id = str(contract.metadata.get("control_center", {}).get("selected_plan", {}).get("plan_id", ""))
    if plan_id:
        task_types, risk_level = _plan_bucket(contract)
        record_plan_outcome(plan_id, "failure", task_types=task_types, risk_level=risk_level)
    _refresh_task_summary(
        args.task_id,
        state=state,
        extra={
            "last_failure": {
                "stage": stage_name,
                "error": args.error,
                "recovery": recovery,
                "recurrence": recurrence,
            }
        },
    )
    log_event(args.task_id, "stage_failed", stage=stage_name, error=args.error, recovery=recovery, recurrence=recurrence)
    record_error(args.task_id, f"{stage_name}: {args.error}")
    print(json.dumps({"status": "recovering", "recovery": recovery, "recurrence": recurrence}, ensure_ascii=False, indent=2))
    return 0


def verify_task(args: argparse.Namespace) -> int:
    contract = load_contract(args.task_id)
    state = load_state(args.task_id)
    results = []
    all_ok = True
    verified_stages = []
    for stage_contract in contract.stages:
        if not stage_contract.verifier:
            continue
        result = run_verifier(stage_contract.verifier)
        results.append({"stage": stage_contract.name, "result": result})
        stage_state = state.stages[stage_contract.name]
        stage_state.verification_status = result["status"]
        stage_state.updated_at = utc_now_iso()
        if not result["ok"]:
            all_ok = False
            stage_state.status = "failed"
            stage_state.blocker = f"verification failed: {result['status']}"
        else:
            verified_stages.append(stage_contract.name)
            if stage_state.status != "completed":
                stage_state.status = "completed"
                stage_state.summary = stage_state.summary or f"Verifier passed for {stage_contract.name}"
                stage_state.completed_at = utc_now_iso()
    state.status = "completed" if all_ok else "recovering"
    state.next_action = "none" if all_ok else "repair_verification_failure"
    state.blockers = [] if all_ok else ["verification_failure"]
    if all_ok:
        next_stage = None
        for name in state.stage_order:
            if state.stages[name].status != "completed":
                next_stage = name
                break
        if next_stage:
            state.status = "planning"
            state.current_stage = next_stage
            state.next_action = f"start_stage:{next_stage}"
        else:
            state.current_stage = ""
    state.last_update_at = utc_now_iso()
    save_state(state)
    plan_id = str(contract.metadata.get("control_center", {}).get("selected_plan", {}).get("plan_id", ""))
    if plan_id:
        task_types, risk_level = _plan_bucket(contract)
        record_plan_outcome(plan_id, "success" if all_ok else "failure", task_types=task_types, risk_level=risk_level)
    _refresh_task_summary(
        args.task_id,
        state=state,
        extra={"verified_stages": verified_stages, "verification_results": results, "verification_ok": all_ok},
    )
    log_event(args.task_id, "verification_ran", ok=all_ok, results=results, verified_stages=verified_stages)
    print(json.dumps({"ok": all_ok, "results": results, "verified_stages": verified_stages, "status": state.status, "next_action": state.next_action}, ensure_ascii=False, indent=2))
    return 0


def checkpoint_task(args: argparse.Namespace) -> int:
    state = load_state(args.task_id)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = checkpoints_dir(args.task_id) / f"{stamp}.txt"
    text = write_checkpoint(path, state)
    log_event(args.task_id, "checkpoint_written", path=str(path))
    print(json.dumps({"path": str(path), "text": text}, ensure_ascii=False, indent=2))
    return 0


def set_stage_verifier(args: argparse.Namespace) -> int:
    contract = load_contract(args.task_id)
    stage = next((item for item in contract.stages if item.name == args.stage), None)
    if not stage:
        raise SystemExit("unknown stage")
    stage.verifier = json.loads(args.verifier_json)
    save_contract(contract)
    log_event(args.task_id, "stage_verifier_updated", stage=args.stage, verifier=stage.verifier)
    print(json.dumps({"task_id": args.task_id, "stage": args.stage, "verifier": stage.verifier}, ensure_ascii=False, indent=2))
    return 0


def evolve_task(args: argparse.Namespace) -> int:
    state = load_state(args.task_id)
    proposal = {
        "task_id": args.task_id,
        "proposed_at": utc_now_iso(),
        "reason": args.reason,
        "current_blockers": state.blockers,
        "learning_backlog": state.learning_backlog,
        "suggested_runtime_changes": [
            "add stronger verifier",
            "add recovery branch",
            "promote recurring fix into durable guidance",
        ],
    }
    report_path = task_dir(args.task_id) / "runtime-evolution-proposal.json"
    write_json(report_path, proposal)
    log_event(args.task_id, "runtime_evolution_proposed", path=str(report_path))
    print(json.dumps({"path": str(report_path), "proposal": proposal}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="General autonomy runtime for long-running OpenClaw tasks")
    sub = parser.add_subparsers(dest="cmd", required=True)

    create = sub.add_parser("create")
    create.add_argument("--task-id", required=True)
    create.add_argument("--goal", required=True)
    create.add_argument("--done-definition", required=True)
    create.add_argument("--stage", action="append", required=True, help="Format: name|goal")
    create.add_argument("--hard-constraint", action="append")
    create.add_argument("--soft-preference", action="append")
    create.add_argument("--allowed-tool", action="append")
    create.add_argument("--forbidden-action", action="append")

    status = sub.add_parser("status")
    status.add_argument("--task-id", required=True)

    sub.add_parser("list")

    run_once_cmd = sub.add_parser("run-once")
    run_once_cmd.add_argument("--task-id", required=True)

    recover = sub.add_parser("recover-stage")
    recover.add_argument("--task-id", required=True)
    recover.add_argument("--stage", default="")
    recover.add_argument("--summary", required=True)

    apply_recover = sub.add_parser("apply-recovery")
    apply_recover.add_argument("--task-id", required=True)
    apply_recover.add_argument("--stage", default="")
    apply_recover.add_argument("--action", default="")

    complete = sub.add_parser("complete-stage")
    complete.add_argument("--task-id", required=True)
    complete.add_argument("--stage", default="")
    complete.add_argument("--summary", required=True)

    fail = sub.add_parser("fail-stage")
    fail.add_argument("--task-id", required=True)
    fail.add_argument("--stage", default="")
    fail.add_argument("--error", required=True)

    verify = sub.add_parser("verify")
    verify.add_argument("--task-id", required=True)

    checkpoint = sub.add_parser("checkpoint")
    checkpoint.add_argument("--task-id", required=True)

    set_verifier = sub.add_parser("set-stage-verifier")
    set_verifier.add_argument("--task-id", required=True)
    set_verifier.add_argument("--stage", required=True)
    set_verifier.add_argument("--verifier-json", required=True)

    evolve = sub.add_parser("propose-evolution")
    evolve.add_argument("--task-id", required=True)
    evolve.add_argument("--reason", required=True)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.cmd == "create":
        return create_task(args)
    if args.cmd == "status":
        return status_task(args)
    if args.cmd == "list":
        return list_tasks(args)
    if args.cmd == "run-once":
        return run_once(args)
    if args.cmd == "recover-stage":
        return recover_task(args)
    if args.cmd == "apply-recovery":
        return apply_recovery(args)
    if args.cmd == "complete-stage":
        return complete_stage(args)
    if args.cmd == "fail-stage":
        return fail_stage(args)
    if args.cmd == "verify":
        return verify_task(args)
    if args.cmd == "checkpoint":
        return checkpoint_task(args)
    if args.cmd == "set-stage-verifier":
        return set_stage_verifier(args)
    if args.cmd == "propose-evolution":
        return evolve_task(args)
    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
