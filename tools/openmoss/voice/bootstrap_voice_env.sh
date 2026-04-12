#!/bin/zsh
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
# 中文说明：
# - 文件路径：`tools/openmoss/voice/bootstrap_voice_env.sh`
# - 文件作用：负责`bootstrap_voice_env` 相关的一方系统逻辑。
# - 包含 shell 函数：无显式 shell 函数。
#

set -euo pipefail

ROOT="/Users/mac_claw/.openclaw/workspace/tools/openmoss/voice"
VENV="$ROOT/.venv"
PYTHON_BIN="${PYTHON_BIN:-/opt/homebrew/bin/python3.11}"
INSTALL_CPU_STACK="${INSTALL_CPU_STACK:-0}"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "python not found: $PYTHON_BIN" >&2
  exit 1
fi

"$PYTHON_BIN" -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip

if [ "$INSTALL_CPU_STACK" = "1" ]; then
  "$VENV/bin/pip" install \
    numpy \
    scipy \
    soundfile \
    librosa \
    orjson \
    PyYAML \
    einops \
    tiktoken \
    tqdm \
    requests \
    safetensors \
    gradio \
    packaging \
    psutil \
    ninja \
    wheel \
    setuptools \
    transformers \
    torch \
    torchaudio
fi

echo "voice venv ready: $VENV"
if [ "$INSTALL_CPU_STACK" = "1" ]; then
  echo "CPU inference stack installed into: $VENV"
else
  echo "MOSS-TTS itself is not installed automatically here because model/runtime choice"
  echo "depends on your GPU/CPU plan. Use INSTALL_CPU_STACK=1 for a local CPU stack."
fi
