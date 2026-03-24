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

## Validation

- [ ] `jinclaw-status`
- [ ] `jinclaw-doctor`
- [ ] `jinclaw-upgrade-check`
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

- [ ] Ready for `Squash and merge`
- [ ] Safe to land on `main`
