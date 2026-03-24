# Stage Checkpoint Template

Use this at the end of every meaningful stage.

Apply the shared monitoring standard from `../../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md`.

```text
Current stage:
Completed:
Not completed:
Acceptance check result:
Primary monitor:
Backstop monitor:
Miss-detection signal:
Risks / issues:
Blind spots / confidence limits:
Suggested next step:
Continuation mode: auto-continue | wait-for-confirmation
```

## Notes

- Keep it short but concrete.
- If blocked, say exactly what blocked progress.
- If continuing automatically, explain why it is safe to continue.
- If the primary monitor was weak, name the compensating control instead of pretending certainty.
