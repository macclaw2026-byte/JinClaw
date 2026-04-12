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
- 文件路径：`tools/openmoss/voice/adapter.py`
- 文件作用：负责`adapter` 相关的一方系统逻辑。
- 顶层函数：load_voice_config、ensure_voice_layout、build_moss_tts_command、build_moss_ttsd_command、run_command、build_ttsd_input_jsonl。
- 顶层类：VoiceConfig。
- 阅读建议：先看模块说明，再按函数/类 docstring 顺着主流程理解调用关系。
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List


VOICE_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/voice")
VOICE_RUNTIME_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/voice")
DEFAULT_TTS_REPO = Path("/tmp/openmoss-inspect/MOSS-TTS")
DEFAULT_TTSD_REPO = Path("/tmp/openmoss-inspect/MOSS-TTSD")


@dataclass
class VoiceConfig:
    """
    中文注解：
    - 功能：封装 `VoiceConfig` 对应的数据结构或行为对象。
    - 角色：属于本模块中的对外可见逻辑，通常由上游流程实例化后参与状态流转或能力执行。
    - 调用关系：请结合模块级说明与类方法一起阅读，理解它在主链中的位置。
    """
    dry_run: bool
    backend: str
    tts_repo: Path
    ttsd_repo: Path
    output_dir: Path
    model_path: str
    ttsd_model_path: str
    codec_model_path: str


def load_voice_config() -> VoiceConfig:
    """
    中文注解：
    - 功能：实现 `load_voice_config` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    local = VOICE_ROOT / "config.local.json"
    raw = {
        "dry_run": True,
        "backend": "library",
        "tts_repo": str(DEFAULT_TTS_REPO),
        "ttsd_repo": str(DEFAULT_TTSD_REPO),
        "output_dir": str(VOICE_RUNTIME_ROOT / "outputs"),
        "model_path": "OpenMOSS-Team/MOSS-TTS",
        "ttsd_model_path": "OpenMOSS-Team/MOSS-TTSD-v1.0",
        "codec_model_path": "OpenMOSS-Team/MOSS-Audio-Tokenizer",
    }
    if local.exists():
        raw.update(json.loads(local.read_text(encoding="utf-8")))
    return VoiceConfig(
        dry_run=bool(raw["dry_run"]),
        backend=str(raw["backend"]),
        tts_repo=Path(str(raw["tts_repo"])).expanduser(),
        ttsd_repo=Path(str(raw["ttsd_repo"])).expanduser(),
        output_dir=Path(str(raw["output_dir"])).expanduser(),
        model_path=str(raw["model_path"]),
        ttsd_model_path=str(raw["ttsd_model_path"]),
        codec_model_path=str(raw["codec_model_path"]),
    )


def ensure_voice_layout(cfg: VoiceConfig) -> None:
    """
    中文注解：
    - 功能：实现 `ensure_voice_layout` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    cfg.output_dir.mkdir(parents=True, exist_ok=True)


def build_moss_tts_command(cfg: VoiceConfig, text: str, output_wav: Path) -> List[str]:
    """
    中文注解：
    - 功能：实现 `build_moss_tts_command` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if cfg.backend == "library":
        script = VOICE_ROOT / "run_moss_tts.py"
        return [
            "python3",
            str(script),
            "--text",
            text,
            "--output",
            str(output_wav),
            "--tts-repo",
            str(cfg.tts_repo),
            "--model-path",
            cfg.model_path,
            "--codec-model-path",
            cfg.codec_model_path,
        ]
    script = cfg.tts_repo / "clis" / "moss_tts_app.py"
    return ["python3", str(script), "--help"] if script.exists() else ["python3", "-c", "print('MOSS-TTS missing')"]


def build_moss_ttsd_command(cfg: VoiceConfig, input_jsonl: Path, save_dir: Path) -> List[str]:
    """
    中文注解：
    - 功能：实现 `build_moss_ttsd_command` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    script = cfg.ttsd_repo / "inference.py"
    return [
        "python3",
        str(script),
        "--model_path",
        cfg.ttsd_model_path,
        "--codec_model_path",
        cfg.codec_model_path,
        "--save_dir",
        str(save_dir),
        "--input_jsonl",
        str(input_jsonl),
    ] if script.exists() else ["python3", "-c", "print('MOSS-TTSD missing')"]


def run_command(command: List[str], dry_run: bool) -> dict:
    """
    中文注解：
    - 功能：实现 `run_command` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    if dry_run:
        return {"ok": True, "dry_run": True, "command": command}
    completed = subprocess.run(command, capture_output=True, text=True)
    return {
        "ok": completed.returncode == 0,
        "dry_run": False,
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def build_ttsd_input_jsonl(lines: List[dict]) -> Path:
    """
    中文注解：
    - 功能：实现 `build_ttsd_input_jsonl` 对应的处理逻辑。
    - 角色：属于本模块中的对外可见逻辑；私有函数通常服务同文件主流程，公共函数通常作为跨模块入口或能力接口。
    - 调用关系：建议结合本文件的模块说明、调用方以及同名相关辅助函数一起阅读。
    """
    fd, tmp_name = tempfile.mkstemp(prefix="moss-ttsd-", suffix=".jsonl")
    tmp_path = Path(tmp_name)
    with open(tmp_path, "w", encoding="utf-8") as fh:
        for line in lines:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    try:
        Path(f"/dev/fd/{fd}").exists()
    finally:
        try:
            import os
            os.close(fd)
        except OSError:
            pass
    return tmp_path
