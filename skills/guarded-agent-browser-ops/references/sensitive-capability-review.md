# Sensitive Capability Review Plan

Use this before allowing any restricted `agent-browser` capability.

Apply the shared monitoring standard from `../../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md`.

## Trigger conditions

Run a second review if the planned command or workflow touches any of:

- `state save`
- `state load`
- cookie listing / setting / clearing on authenticated sites
- localStorage / sessionStorage inspection on authenticated sites
- credentials / basic auth
- browser-profile import
- remote-debugging-based auth import
- any command that would persist auth/session material to disk

## Review questions

1. Why is this capability necessary for the task?
2. Can the task be completed without it?
3. Will the data remain local only?
4. Will any token/cookie/session material be logged, exported, or forwarded?
5. What exact files or paths will store sensitive state?
6. Can the state be deleted immediately after use?
7. Is there a lower-sensitivity fallback?
8. What is the primary monitor that keeps this usage bounded?
9. What backstop verifies sensitive state was not retained or leaked?

## Decision outcomes

### Allow for this task
Only if:
- necessary
- local only
- not logged or forwarded
- storage path is known
- cleanup path is defined
- backstop verification is defined

### Do not allow
If:
- the capability is unnecessary
- state handling is opaque
- secrets may be exposed
- audit trail is insufficient
- no trustworthy backstop exists

## Post-use requirements

If allowed:
- record what sensitive capability was used
- record where state was stored
- record cleanup / rollback steps
- verify cleanup actually happened
- tell the user plainly what happened
