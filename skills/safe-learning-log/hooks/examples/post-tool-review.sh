#!/bin/bash
set -e
OUTPUT="${CLAUDE_TOOL_OUTPUT:-}"
if [[ "$OUTPUT" == *"error"* || "$OUTPUT" == *"Error"* || "$OUTPUT" == *"failed"* || "$OUTPUT" == *"FAILED"* ]]; then
cat << 'EOF'
<safe-learning-log-error-review>
A failure was detected.

Review it through the shared monitoring-and-retrofit framework:
- was the failure already monitored?
- was a backstop missing or too weak?
- does this belong in one skill, many skills, or shared runtime policy?

If this becomes a durable fix, log it to .learnings/ERRORS.md.
If it changes workflow, hooks, skills, or other high-impact files, also create a change report in .learnings/reports/ and summarize it to the user.
</safe-learning-log-error-review>
EOF
fi
