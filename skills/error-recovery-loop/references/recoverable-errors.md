# Recoverable Error Patterns

Use the shared monitoring standard from `../../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md` when classifying whether an error was merely operational or revealed a monitoring gap.

## Common recoverable errors

### Exact-text edit mismatch
- cause: file changed or expected text was slightly wrong
- likely monitor issue: exact-state assumption was stale
- recovery: re-read the file, patch exact current text, verify
- backstop: re-read after patch and confirm intended diff

### Permission denied on local binary
- cause: executable bit missing
- likely monitor issue: execution-readiness check missing
- recovery: chmod +x then retry
- backstop: rerun and confirm expected output exists

### Incomplete/weak web page fetch
- cause: dynamic page, wrong source, shell page only
- likely monitor issue: completeness or rendering monitor failed
- recovery: switch source or use browser rendering / resilient research flow
- backstop: cross-check against a stronger source before concluding

### Missing directory/path
- cause: path not created yet
- likely monitor issue: prerequisite/path validation missing
- recovery: create directories or correct path
- backstop: confirm the expected artifact now lands in the intended location

## Non-recoverable or escalation-needed patterns

- suspected secret leakage
- security boundary violation
- destructive action uncertainty
- unknown binary behavior

## Rule

If the same error pattern recurs, treat it as more than a one-off repair: decide whether one skill, multiple skills, or the shared runtime framework should inherit the fix.
