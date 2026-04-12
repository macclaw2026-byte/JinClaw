#!/bin/zsh
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
# 中文说明：
# - 文件路径：`tools/openmoss/voice/start_voice_doctor.sh`
# - 文件作用：负责`start_voice_doctor` 相关的一方系统逻辑。
# - 包含 shell 函数：无显式 shell 函数。
#

set -euo pipefail

source /Users/mac_claw/.openclaw/workspace/tools/openmoss/ops/openmoss_launch_env.sh

ROOT="/Users/mac_claw/.openclaw/workspace/tools/openmoss/voice"
VENV="$ROOT/.venv"

if [ ! -x "$VENV/bin/python" ]; then
  echo "missing voice venv; run $ROOT/bootstrap_voice_env.sh first" >&2
  exit 1
fi

exec "$VENV/bin/python" "$ROOT/generate_voice.py" doctor
