#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


WORKSPACE_ROOT = Path("/Users/mac_claw/.openclaw/workspace")
OPENMOSS_ROOT = WORKSPACE_ROOT / "tools/openmoss"
EXCLUDED_PARTS = {".venv", "site-packages", "node_modules", "__pycache__", "generated_capabilities"}
TARGET_EXTENSIONS = {".py", ".sh"}


@dataclass
class ModuleInfo:
    path: Path
    relative_path: str
    top_level_functions: list[str]
    top_level_classes: list[str]


ROLE_HINTS = {
    "brain_router": "聊天指令路由、任务切根与会话绑定决策",
    "brain_enforcer": "主会话回执补偿与脑路由兜底执行",
    "system_doctor": "任务级医生诊断、修复与升级回执",
    "mission_supervisor": "任务监督、空转识别与推进纠偏",
    "progress_evidence": "判断任务是否存在真实进展证据",
    "run_liveness_verifier": "解释 waiting_external 所等待的 run 是否仍然存活",
    "control_plane_builder": "统一控制平面的快照构建与多源状态汇总",
    "task_status_snapshot": "为回复与诊断生成权威任务状态快照",
    "task_receipt_engine": "任务型指令的即时回执生成与发送",
    "mission_loop": "控制中心每轮任务推进决策",
    "orchestrator": "把用户目标编排成可执行任务包与阶段合同",
    "intent_analyzer": "识别目标意图、风险与能力需求",
    "proposal_judge": "给候选方案打分并选定执行方案",
    "route_guardrails": "路由守卫、切根与主题纠偏",
    "response_policy_engine": "把内部状态翻译成对用户可见的真实回复",
    "response_drift_detector": "拦截回复与权威状态漂移",
    "canonical_active_task": "解析会话当前唯一权威活跃任务",
    "task_lifecycle": "任务生命周期分层：active、warm、archive、quarantine",
    "context_builder": "为 AI 执行阶段整理上下文包",
    "runtime_service": "自治运行时主循环，负责推进、验证、恢复与医生接管",
    "manager": "任务 contract/state 的读写、事件记录与生命周期更新",
    "action_executor": "阶段执行派发、运行轮询与执行状态回写",
    "preflight_engine": "执行前检查、风险门控与历史 guard 套用",
    "recovery_engine": "失败分类、恢复动作生成与恢复执行",
    "learning_engine": "错误、学习与任务摘要的结构化沉淀",
    "promotion_engine": "把重复错误升级为 durable runtime rule",
    "telegram_binding": "Telegram 消息接入与任务绑定入口",
    "task_ingress": "显式任务创建入口与 root mission 启动器",
    "task_contract": "任务合同与阶段合同的数据结构定义",
    "task_state": "任务状态与阶段状态的数据结构定义",
    "verifier_registry": "任务验证器注册与校验执行",
    "bridge_service": "桥接服务主循环，负责收件、派发与发件",
    "reply_router": "桥接层回复路由与消息分发",
    "dispatch_to_openclaw": "把桥接消息投递给 OpenClaw/JinClaw",
    "deliver_outbox": "桥接层对外发送队列处理",
    "process_queue": "桥接层队列消费与标准化处理",
    "jinclaw_ops": "运维诊断、系统体检与运维脚本入口",
}


def is_first_party_code(path: Path) -> bool:
    if path.suffix not in TARGET_EXTENSIONS:
        return False
    return not any(part in EXCLUDED_PARTS for part in path.parts)


def iter_target_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if is_first_party_code(path):
            yield path


def summarize_role(path: Path) -> str:
    stem = path.stem
    if stem in ROLE_HINTS:
        return ROLE_HINTS[stem]
    parent = path.parent.name
    if parent == "control_center":
        return f"控制中心中与 `{stem}` 相关的编排、分析或决策逻辑"
    if parent == "autonomy":
        return f"自治运行时中与 `{stem}` 相关的执行或状态管理逻辑"
    if parent == "bridge":
        return f"桥接层中与 `{stem}` 相关的消息同步与投递逻辑"
    if parent == "ops":
        return f"运维脚本中与 `{stem}` 相关的诊断、启动或修复逻辑"
    return f"`{stem}` 相关的一方系统逻辑"


def parse_python_module(path: Path) -> ModuleInfo:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    top_level_functions: list[str] = []
    top_level_classes: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            top_level_functions.append(node.name)
        elif isinstance(node, ast.ClassDef):
            top_level_classes.append(node.name)
    return ModuleInfo(
        path=path,
        relative_path=str(path.relative_to(WORKSPACE_ROOT)),
        top_level_functions=top_level_functions,
        top_level_classes=top_level_classes,
    )


def build_module_docstring(info: ModuleInfo) -> str:
    function_list = "、".join(info.top_level_functions) if info.top_level_functions else "无顶层函数"
    class_list = "、".join(info.top_level_classes) if info.top_level_classes else "无顶层类"
    return (
        '"""\n'
        "中文说明：\n"
        f"- 文件路径：`{info.relative_path}`\n"
        f"- 文件作用：负责{summarize_role(info.path)}。\n"
        f"- 顶层函数：{function_list}。\n"
        f"- 顶层类：{class_list}。\n"
        "- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。\n"
        '"""\n'
    )


def build_callable_docstring(name: str, kind: str, is_private: bool) -> str:
    role_text = "内部辅助逻辑" if is_private else "对外可见逻辑"
    if kind == "class":
        return (
            '"""\n'
            "中文注解：\n"
            f"- 功能：封装 `{name}` 对应的数据结构或行为对象。\n"
            f"- 角色：属于本模块中的{role_text}，通常由上游流程实例化后参与状态流转或能力执行。\n"
            "- 调用关系：请结合模块级说明与类方法一起阅读，理解它在主链中的位置。\n"
            '"""\n'
        )
    return (
        '"""\n'
        "中文注解：\n"
        f"- 功能：实现 `{name}` 对应的处理逻辑。\n"
        f"- 角色：属于本模块中的{role_text}；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。\n"
        "- 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。\n"
        '"""\n'
    )


def annotate_python_file(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    tree = ast.parse(original)
    lines = original.splitlines(keepends=True)
    inserts: dict[int, str] = {}

    if ast.get_docstring(tree, clean=False) is None:
        info = parse_python_module(path)
        module_doc = build_module_docstring(info)
        insert_line = 0
        if lines and lines[0].startswith("#!"):
            insert_line = 1
            while insert_line < len(lines) and lines[insert_line].strip() == "":
                insert_line += 1
        inserts[insert_line] = module_doc + ("\n" if insert_line and (insert_line >= len(lines) or lines[insert_line - 1].strip()) else "")

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if ast.get_docstring(node, clean=False) is not None:
            continue
        if not getattr(node, "body", None):
            continue
        first_stmt = node.body[0]
        indent = " " * (first_stmt.col_offset if hasattr(first_stmt, "col_offset") else (node.col_offset + 4))
        kind = "class" if isinstance(node, ast.ClassDef) else "function"
        doc = build_callable_docstring(node.name, kind, node.name.startswith("_"))
        doc = "".join(indent + line + ("\n" if not line.endswith("\n") else "") for line in doc.splitlines())
        inserts[first_stmt.lineno - 1] = doc

    if not inserts:
        return False

    new_lines: list[str] = []
    for index, line in enumerate(lines):
        if index in inserts:
            new_lines.append(inserts[index])
        new_lines.append(line)
    if len(lines) in inserts:
        new_lines.append(inserts[len(lines)])

    updated = "".join(new_lines)
    if updated == original:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def parse_shell_functions(lines: list[str]) -> list[str]:
    names: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.endswith("() {") and not stripped.startswith("#"):
            names.append(stripped.split("()", 1)[0].strip())
    return names


def annotate_shell_file(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    changed = False
    func_names = parse_shell_functions(lines)
    header = [
        "# 中文说明：\n",
        f"# - 文件路径：`{path.relative_to(WORKSPACE_ROOT)}`\n",
        f"# - 文件作用：负责{summarize_role(path)}。\n",
        f"# - 包含 shell 函数：{'、'.join(func_names) if func_names else '无显式 shell 函数'}。\n",
    ]

    insert_at = 0
    if lines and lines[0].startswith("#!"):
        insert_at = 1
    has_header = any("中文说明：" in line for line in lines[: min(len(lines), insert_at + 6)])
    if not has_header:
        lines[insert_at:insert_at] = header + (["#\n"] if insert_at < len(lines) else [])
        changed = True

    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.endswith("() {") and not stripped.startswith("#"):
            prev = output[-1] if output else ""
            if "中文注解：" not in prev:
                func_name = stripped.split("()", 1)[0].strip()
                output.append("# 中文注解：\n")
                output.append(f"# - 功能：实现 shell 函数 `{func_name}` 的处理逻辑。\n")
                output.append("# - 调用关系：通常由本脚本主流程或其他 shell 入口按顺序调用。\n")
                changed = True
        output.append(line)

    updated = "".join(output)
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        return True
    return changed


def main() -> int:
    changed_files: list[str] = []
    for path in iter_target_files(OPENMOSS_ROOT):
        if path.suffix == ".py":
            changed = annotate_python_file(path)
        elif path.suffix == ".sh":
            changed = annotate_shell_file(path)
        else:
            changed = False
        if changed:
            changed_files.append(str(path.relative_to(WORKSPACE_ROOT)))
    print(f"annotated_files={len(changed_files)}")
    for item in changed_files:
        print(item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
