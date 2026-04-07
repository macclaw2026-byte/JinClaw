## Summary

- What changed?
- Why is this needed?

## Risk Level

- [ ] Low
- [ ] Medium
- [ ] High

## JinClaw Areas Touched

- [ ] Control center
- [ ] Autonomy runtime
- [ ] Brain routing
- [ ] Recovery / preflight
- [ ] Ops / launchd / self-heal
- [ ] Upstream monitoring
- [ ] Governance / CI

## Doctor Coverage

- [ ] Already covered by the canonical JinClaw doctor
- [ ] Exports signal/artifact into the canonical doctor path
- [ ] Temporary blind spot declared with backstop + retrofit owner

Component:
Direct coverage path:
Exported signal/artifact:
Primary monitor:
Backstop monitor:
Delayed verification:
Blind spot:
Retrofit owner:

## Validation

- [ ] `jinclaw-status`
- [ ] `jinclaw-doctor`
- [ ] `jinclaw-upgrade-check`
- [ ] `jinclaw-pr-ready` (or equivalent scoped PR readiness check)
- [ ] targeted smoke test for changed behavior
- [ ] live-wiring/runtime validation if applicable

Validation notes:

## Security Review

- [ ] No secrets or sensitive local state are included
- [ ] No unsafe fallback behavior was introduced
- [ ] External adoption logic remains auditable and reversible

## Upstream / OSS Intake

- [ ] No upstream behavior borrowed
- [ ] Borrowed idea only
- [ ] Partial adaptation from upstream or OSS
- [ ] Explicit compatibility change

Details:

## Merge Checklist

- [ ] All intended local changes are committed on a dedicated PR branch
- [ ] Remote branch reflects local source-of-truth before merge
- [ ] Ready for `Squash and merge`
- [ ] Safe to land on `main`
