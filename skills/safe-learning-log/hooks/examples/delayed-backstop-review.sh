#!/bin/bash
set -e
cat << 'EOF'
<delayed-backstop-review>
Run a delayed backstop review for work that may have produced shallow success.

Check:
- what primary monitor originally justified success?
- what later signal might reveal a miss?
- which compensating control should run now?
- if a structural gap is found, should it update one skill, multiple skills, or the shared monitoring framework?

If the late review changes a durable workflow, create a change report and log the lesson.
</delayed-backstop-review>
EOF
