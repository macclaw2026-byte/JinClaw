#!/bin/zsh
# 中文说明：
# - 文件路径：`tools/openmoss/ops/start_openclaw_selfheal.sh`
# - 文件作用：负责运维脚本中与 `start_openclaw_selfheal` 相关的诊断、启动或修复逻辑。
# - 包含 shell 函数：无显式 shell 函数。
#
set -euo pipefail

exec /usr/bin/env python3 /Users/mac_claw/.openclaw/workspace/tools/openmoss/ops/openclaw_selfheal.py
