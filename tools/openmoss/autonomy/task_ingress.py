#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from manager import create_task

CONTROL_CENTER_DIR = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/control_center")
if str(CONTROL_CENTER_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER_DIR))

from orchestrator import build_control_center_package


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug[:48] or "autonomy-task"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a generic autonomy task from a plain-language goal")
    parser.add_argument("--goal", required=True)
    parser.add_argument("--task-id", default="")
    parser.add_argument("--done-definition", default="")
    args = parser.parse_args()

    task_id = args.task_id or slugify(args.goal)
    package = build_control_center_package(task_id, args.goal, source="task_ingress")
    done_definition = args.done_definition or str(package["done_definition"])
    create_args = argparse.Namespace(
        task_id=task_id,
        goal=args.goal,
        done_definition=done_definition,
        stage=[],
        stage_json=json.dumps(package["stages"], ensure_ascii=False),
        hard_constraint=package["hard_constraints"],
        soft_preference=[],
        allowed_tool=package["allowed_tools"],
        forbidden_action=[],
        metadata_json=json.dumps(package["metadata"], ensure_ascii=False),
    )
    return create_task(create_args)


if __name__ == "__main__":
    raise SystemExit(main())
