#!/bin/bash
set -e
OUTPUT="${CLAUDE_TOOL_OUTPUT:-}"
if [[ "$OUTPUT" == *"failed"* || "$OUTPUT" == *"Failed"* || "$OUTPUT" == *"error"* || "$OUTPUT" == *"Error"* || "$OUTPUT" == *"permission denied"* || "$OUTPUT" == *"Could not find the exact text"* ]]; then
cat << 'EOF'
<error-recovery-loop>
A recoverable tool/workflow failure may have occurred.

Apply the shared monitoring-and-retrofit framework:
- classify the failure
- identify the primary monitor that should have caught it
- run the backstop or compensating check if needed
- attempt a safe repair
- verify the final state
- if the miss reveals a structural monitoring gap, feed it into safe-learning-log or runtime-evolution-loop

Avoid surfacing noisy intermediate tool errors if the final result is healthy.
</error-recovery-loop>
EOF
fi
