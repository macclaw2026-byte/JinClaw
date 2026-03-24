#!/usr/bin/env python3

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
    dry_run: bool
    backend: str
    tts_repo: Path
    ttsd_repo: Path
    output_dir: Path
    model_path: str
    ttsd_model_path: str
    codec_model_path: str


def load_voice_config() -> VoiceConfig:
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
    cfg.output_dir.mkdir(parents=True, exist_ok=True)


def build_moss_tts_command(cfg: VoiceConfig, text: str, output_wav: Path) -> List[str]:
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
