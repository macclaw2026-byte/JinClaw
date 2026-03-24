#!/bin/bash
set -e
cat << 'EOF'
<product-selection-learning>
A product-selection run has completed.

Review it with the shared monitoring-and-retrofit framework:
- which monitors were most predictive?
- which signals were noisy or misleading?
- did any false positive or false negative slip through?
- does a platform-specific extension now need stronger checks?

Log durable lessons to safe-learning-log and escalate recurring structural patterns to runtime-evolution-loop.
</product-selection-learning>
EOF
