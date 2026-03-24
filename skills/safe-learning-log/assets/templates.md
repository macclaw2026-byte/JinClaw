# Templates

Use the shared monitoring standard from `../../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md` when a learning, error, or change report involves missed signals, compensating controls, or retrofit decisions.

## Files

- `.learnings/LEARNINGS.md`
- `.learnings/ERRORS.md`
- `.learnings/FEATURE_REQUESTS.md`
- `.learnings/reports/CHANGE-YYYYMMDD-HHMMSS-short-name.md`

## Minimal headers

### LEARNINGS.md

```markdown
# Learnings
```

### ERRORS.md

```markdown
# Errors
```

### FEATURE_REQUESTS.md

```markdown
# Feature Requests
```

### Change report

```markdown
# CHANGE-YYYYMMDD-HHMMSS-short-name

## Summary

## Reason

## Files Touched
- 

## Change Details
- added:
- updated:
- removed:

## Rollback
- Easy rollback: yes
- Suggested rollback:
```

## When monitoring matters

When a report involves a miss, false positive, false negative, or delayed review, include:
- primary monitor
- backstop monitor
- blind spot or confidence limit
- retrofit target if the fix should spread beyond one file
