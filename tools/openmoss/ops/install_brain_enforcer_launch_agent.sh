#!/bin/zsh
# 中文说明：
# - 文件路径：`tools/openmoss/ops/install_brain_enforcer_launch_agent.sh`
# - 文件作用：负责运维脚本中与 `install_brain_enforcer_launch_agent` 相关的诊断、启动或修复逻辑。
# - 包含 shell 函数：无显式 shell 函数。
#
set -euo pipefail

SOURCE="/Users/mac_claw/.openclaw/workspace/tools/openmoss/ops/ai.openclaw.brain-enforcer.plist"
TARGET="/Users/mac_claw/Library/LaunchAgents/ai.openclaw.brain-enforcer.plist"
LABEL="ai.openclaw.brain-enforcer"
UID="$(id -u)"

cp "$SOURCE" "$TARGET"
launchctl bootout "gui/${UID}" "$TARGET" >/dev/null 2>&1 || true
launchctl bootstrap "gui/${UID}" "$TARGET"
launchctl kickstart -k "gui/${UID}/${LABEL}"
