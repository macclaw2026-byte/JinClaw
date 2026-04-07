# Task State

## Task
Refactor JinClaw to a single-doctor architecture by folding GStack integration monitoring into the existing system doctor.

## Objective
- Preserve exactly one doctor role in JinClaw.
- Move GStack integration integrity checks into `tools/openmoss/control_center/system_doctor.py`.
- Remove independent-doctor status from `jinclaw-gstack-integration-doctor` and replace it with a compatibility shim or remove it.
- Encode the single-doctor + doctor-coverage-followup rules into constitution, governance runtime, and tests.

## Planned Steps
1. Extend Constitution with single-doctor and mandatory doctor coverage rules.
2. Add doctor coverage policy/registry support in governance runtime.
3. Integrate GStack compatibility checks into `system_doctor.py`.
4. Replace the standalone doctor script with a shim or deprecate it safely.
5. Update tests to assert one-doctor architecture and integrated coverage.
6. Run full test suite and record evidence.

## Last Updated
2026-04-06T05:17:00Z
