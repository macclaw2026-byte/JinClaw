#!/usr/bin/env python3

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
    return datetime.utcnow().strftime("%Y%m%dT%H%M%S")


def cmd_summary(args: argparse.Namespace) -> int:
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
