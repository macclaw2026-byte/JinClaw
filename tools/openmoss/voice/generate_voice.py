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
- 文件路径：`tools/openmoss/voice/generate_voice.py`
- 文件作用：负责`generate_voice` 相关的一方系统逻辑。
- 顶层函数：_stamp、cmd_summary、cmd_dialog、build_parser、main。
- 顶层类：无顶层类。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from adapter import (
    VOICE_RUNTIME_ROOT,
    build_moss_tts_command,
    build_moss_ttsd_command,
    build_ttsd_input_jsonl,
    ensure_voice_layout,
    load_voice_config,
    run_command,
)


def _stamp() -> str:
    """
    中文注解：
    - 功能：实现 `_stamp` 对应的处理逻辑。
    - 角色：属于本模块中的内部辅助逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    return datetime.utcnow().strftime("%Y%m%dT%H%M%S")


def cmd_summary(args: argparse.Namespace) -> int:
    """
    中文注解：
    - 功能：实现 `cmd_summary` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    cfg = load_voice_config()
    ensure_voice_layout(cfg)
    out_path = cfg.output_dir / f"summary-{_stamp()}.wav"
    command = build_moss_tts_command(cfg, args.text, out_path)
    result = run_command(command, cfg.dry_run)
    payload = {
        "mode": "summary_tts",
        "output_path": str(out_path),
        "result": result,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_dialog(args: argparse.Namespace) -> int:
    """
    中文注解：
    - 功能：实现 `cmd_dialog` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    cfg = load_voice_config()
    ensure_voice_layout(cfg)
    save_dir = cfg.output_dir / f"dialog-{_stamp()}"
    save_dir.mkdir(parents=True, exist_ok=True)
    items = []
    for idx, line in enumerate(args.line, start=1):
        speaker, text = line.split(":", 1)
        items.append(
            {
                "id": f"dialog-{idx}",
                "conversation": [
                    {"role": speaker.strip(), "text": text.strip()}
                ],
            }
        )
    input_jsonl = build_ttsd_input_jsonl(items)
    command = build_moss_ttsd_command(cfg, input_jsonl, save_dir)
    result = run_command(command, cfg.dry_run)
    payload = {
        "mode": "dialog_tts",
        "save_dir": str(save_dir),
        "input_jsonl": str(input_jsonl),
        "result": result,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """
    中文注解：
    - 功能：实现 `build_parser` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    parser = argparse.ArgumentParser(description="Local OpenMOSS voice adapter")
    sub = parser.add_subparsers(dest="cmd", required=True)

    summary = sub.add_parser("summary")
    summary.add_argument("--text", required=True)

    sub.add_parser("status")

    dialog = sub.add_parser("dialog")
    dialog.add_argument(
        "--line",
        action="append",
        required=True,
        help="Format: speaker:text",
    )
    sub.add_parser("doctor")
    return parser


def main() -> int:
    """
    中文注解：
    - 功能：实现 `main` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    parser = build_parser()
    args = parser.parse_args()
    if args.cmd == "summary":
        return cmd_summary(args)
    if args.cmd == "dialog":
        return cmd_dialog(args)
    if args.cmd == "status":
        cfg = load_voice_config()
        ensure_voice_layout(cfg)
        payload = {
            "dry_run": cfg.dry_run,
            "backend": cfg.backend,
            "tts_repo": str(cfg.tts_repo),
            "ttsd_repo": str(cfg.ttsd_repo),
            "output_dir": str(cfg.output_dir),
            "model_path": cfg.model_path,
            "ttsd_model_path": cfg.ttsd_model_path,
            "codec_model_path": cfg.codec_model_path,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "doctor":
        cfg = load_voice_config()
        ensure_voice_layout(cfg)
        check = {
            "dry_run": cfg.dry_run,
            "backend": cfg.backend,
            "tts_repo_exists": cfg.tts_repo.exists(),
            "ttsd_repo_exists": cfg.ttsd_repo.exists(),
            "output_dir_exists": cfg.output_dir.exists(),
        }
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import importlib.util, json;"
                    "mods=['torch','torchaudio','transformers','numpy','soundfile','librosa'];"
                    "print(json.dumps({m: bool(importlib.util.find_spec(m)) for m in mods}))"
                ),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        check["python_ok"] = probe.returncode == 0
        check["module_probe"] = probe.stdout.strip() or probe.stderr.strip()
        print(json.dumps(check, ensure_ascii=False, indent=2))
        return 0
    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
