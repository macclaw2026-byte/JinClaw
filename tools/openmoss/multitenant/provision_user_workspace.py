#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/multitenant")
TEMPLATE_ROOT = ROOT / "templates" / "commonworkspace"
RUNTIME_ROOT = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/users")


def _replace_tokens(text: str, user_id: str, user_name: str) -> str:
    return text.replace("{{USER_ID}}", user_id).replace("{{USER_NAME}}", user_name)


def _copy_template(dst: Path, user_id: str, user_name: str) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for src in TEMPLATE_ROOT.rglob("*"):
        rel = src.relative_to(TEMPLATE_ROOT)
        target = dst / rel
        if src.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        content = src.read_text(encoding="utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_replace_tokens(content, user_id, user_name), encoding="utf-8")


def _runtime_openclaw_json(dst: Path, user_id: str, user_name: str) -> Path:
    shared = json.loads((TEMPLATE_ROOT / "openclaw.json").read_text(encoding="utf-8"))
    shared.setdefault("openmoss", {})
    shared["openmoss"]["user"] = {
        "id": user_id,
        "name": user_name,
        "workspaceRoot": str(dst),
    }
    runtime_dir = dst / ".tfclaw-openclaw"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    out = runtime_dir / "openclaw.json"
    out.write_text(json.dumps(shared, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def provision(user_id: str, user_name: str, force: bool) -> dict:
    dst = RUNTIME_ROOT / user_id
    if dst.exists() and force:
        shutil.rmtree(dst)
    elif dst.exists() and not force:
        raise FileExistsError(f"workspace already exists: {dst}")
    _copy_template(dst, user_id, user_name)
    config_path = _runtime_openclaw_json(dst, user_id, user_name)
    return {
        "user_id": user_id,
        "user_name": user_name,
        "workspace_root": str(dst),
        "runtime_config": str(config_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision an isolated OpenMOSS/OpenClaw user workspace")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--user-name", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    result = provision(args.user_id, args.user_name, args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
