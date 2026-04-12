#!/bin/zsh
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
# 中文说明：
# - 文件路径：`tools/openmoss/autonomy/start_runtime_service.sh`
# - 文件作用：负责自治运行时中与 `start_runtime_service` 相关的执行或状态管理逻辑。
# - 包含 shell 函数：无显式 shell 函数。
#

set -euo pipefail

ROOT="/Users/mac_claw/.openclaw/workspace/tools/openmoss/autonomy"
source /Users/mac_claw/.openclaw/workspace/tools/openmoss/ops/openmoss_launch_env.sh

exec python3 "$ROOT/runtime_service.py" "$@"
