#!/bin/zsh
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
# 中文说明：
# - 文件路径：`tools/openmoss/ops/start_upstream_watch.sh`
# - 文件作用：负责运维脚本中与 `start_upstream_watch` 相关的诊断、启动或修复逻辑。
# - 包含 shell 函数：无显式 shell 函数。
#
set -euo pipefail

source /Users/mac_claw/.openclaw/workspace/tools/openmoss/ops/openmoss_launch_env.sh

cd /Users/mac_claw
exec /usr/bin/python3 /Users/mac_claw/.openclaw/workspace/tools/openmoss/upstream_watch/watch_updates.py --once
