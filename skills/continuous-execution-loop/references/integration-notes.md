# Integration Notes

## Skill chain

For long tasks, this skill should work with:

1. `self-cognition-orchestrator`
   - interpret task
   - choose best route
   - decide whether other skills are needed

2. `skill-security-audit`
   - audit third-party skills before install

3. `skill-creator`
   - create in-house workflow skills when a safe reusable workflow is missing

4. `safe-learning-log`
   - log stage learnings, errors, feature requests, and change reports

## End-of-task improvement

At the end of the whole task:

- review execution quality
- review blockers and recurring friction
- decide whether any existing in-house skill should be improved
- decide whether any new in-house skill should be created
- write change reports for durable workflow changes

## Monitoring standard

Use `../../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md` as the shared standard for:

- stage monitors
- backstop checks
- miss-detection signals
- retrofit decisions for older skills
