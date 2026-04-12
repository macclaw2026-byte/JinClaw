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
- 文件路径：`tools/openmoss/control_center/local_rebuilder.py`
- 文件作用：负责控制中心中与 `local_rebuilder` 相关的编排、分析或决策逻辑。
- 顶层函数：_write_text、_write_json、rebuild_local_capability、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from paths import GENERATED_CAPABILITIES_ROOT


def _write_text(path: Path, text: str) -> None:
    """
    中文注解：
    - 功能：实现 `_write_text` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: object) -> None:
    """
    中文注解：
    - 功能：实现 `_write_json` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def rebuild_local_capability(task_id: str, spec: Dict[str, object]) -> Dict[str, object]:
    """
    中文注解：
    - 功能：实现 `rebuild_local_capability` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    capability_name = str(spec.get("capability_name", f"{task_id}-local-capability"))
    root = GENERATED_CAPABILITIES_ROOT / capability_name
    manifest = {
        "task_id": task_id,
        "capability_name": capability_name,
        "purpose": spec.get("purpose", ""),
        "inputs": spec.get("inputs", []),
        "outputs": spec.get("outputs", []),
        "must_preserve": spec.get("must_preserve", []),
        "must_improve": spec.get("must_improve", []),
    }
    _write_json(root / "manifest.json", manifest)
    _write_text(
        root / "README.md",
        "\n".join(
            [
                f"# {capability_name}",
                "",
                "This generated local capability is an in-house replacement or enhancement path.",
                "",
                f"Purpose: {spec.get('purpose', '')}",
                "",
                "Behavior goals:",
                *[f"- {item}" for item in spec.get("behavior_goals", [])],
            ]
        ),
    )
    _write_text(
        root / "adapter.py",
        "\n".join(
            [
                "#!/usr/bin/env python3",
                '"""Generated local capability adapter stub."""',
                "",
                "from __future__ import annotations",
                "",
                "def run_local_capability(goal: str, context: dict) -> dict:",
                "    return {",
                "        'status': 'ready_for_in_house_implementation',",
                f"        'capability_name': {capability_name!r},",
                "        'goal': goal,",
                "        'context_keys': sorted(context.keys()),",
                "    }",
                "",
            ]
        ),
    )
    return {
        "task_id": task_id,
        "capability_name": capability_name,
        "root": str(root),
        "manifest_path": str(root / "manifest.json"),
        "adapter_path": str(root / "adapter.py"),
    }


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    import argparse

    parser = argparse.ArgumentParser(description="Rebuild a local in-house capability from a distilled spec")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--spec-json", required=True)
    args = parser.parse_args()
    print(json.dumps(rebuild_local_capability(args.task_id, json.loads(args.spec_json)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
