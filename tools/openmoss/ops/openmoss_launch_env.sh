#!/bin/zsh
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
# 中文说明：
# - 文件路径：`tools/openmoss/ops/openmoss_launch_env.sh`
# - 文件作用：统一补齐 launchd/守护脚本运行时的 PATH 与常用工具目录。
# - 设计意图：
#   1. launchd 默认 PATH 太短，像 `rg` 这类本机工具经常丢失；
#   2. 这里统一收口 Homebrew、系统目录，以及工作区当前实际可用的 ripgrep 目录；
#   3. 所有 start_*.sh 入口共享这一层，避免每个脚本各修各的环境。

setopt local_options null_glob

typeset -a _openmoss_path_parts
typeset -A _openmoss_seen
typeset -a _openmoss_deduped

_openmoss_path_parts=(
  /Users/mac_claw/.vscode/extensions/openai.chatgpt-*/bin/macos-aarch64
  /opt/homebrew/bin
  /opt/homebrew/sbin
  /usr/local/bin
  /usr/bin
  /bin
  /usr/sbin
  /sbin
)

if [[ -n "${PATH:-}" ]]; then
  _openmoss_path_parts+=(${(s/:/)PATH})
fi

for _openmoss_part in $_openmoss_path_parts; do
  [[ -n "$_openmoss_part" ]] || continue
  [[ -d "$_openmoss_part" ]] || continue
  if [[ -z "${_openmoss_seen[$_openmoss_part]-}" ]]; then
    _openmoss_seen[$_openmoss_part]=1
    _openmoss_deduped+=("$_openmoss_part")
  fi
done

export PATH="${(j/:/)_openmoss_deduped}"

unset _openmoss_part
unset _openmoss_path_parts
unset _openmoss_deduped
unset _openmoss_seen
