# AI Optimization Framework

This document is the operational rules-first framework for optimizing, repairing, extending, and evolving JinClaw/OpenClaw.

It is not a replacement for the constitution.
It is the implementation-facing companion to `JINCLAW_CONSTITUTION.md`.

Anyone modifying core OpenClaw/JinClaw files should read both documents first.

## Mandatory Reading Order

1. `JINCLAW_CONSTITUTION.md`
2. `AI_OPTIMIZATION_FRAMEWORK.md`
3. The relevant subsystem README or control model

For most core system changes, that means reading at least one of:

- `tools/openmoss/control_center/README.md`
- `tools/openmoss/control_center/doctor_coverage_contract.md`
- `tools/openmoss/control_center/jinclaw_complex_task_control_model.md`
- `tools/openmoss/control_center/jinclaw_stability_model.md`
- `tools/openmoss/autonomy/README.md`

## Why This Exists

JinClaw already has a constitution, a control center, a canonical doctor, governance modules, recovery loops, learning loops, and runtime evolution mechanisms.

Those pieces were structurally present, but not yet collected into one explicit optimization workflow that every future modifier must follow before changing the system.

This document makes that workflow explicit.

## Non-Negotiable System Rules

1. Rules-first, not patch-first.
   Do not start editing because a local symptom looks obvious. Read the governing rules first.

2. Brain-first.
   Meaningful multi-step instructions, repair missions, and long-running execution must route through the control center instead of bypassing it.

3. One brain, one doctor.
   New features must extend the existing control center and canonical doctor. Do not introduce parallel authorities.

4. Fail closed, not open.
   If a safety, routing, verification, or doctor layer is degraded, the system must say so and refuse unsafe continuation.

5. Evidence over narration.
   Progress means stage evidence, execution traces, verifier output, durable learning, or concrete runtime artifacts.

6. Optimize by evolution, not drift.
   Improvements should strengthen contracts, doctor coverage, recovery, verification, scheduling, and learning. They should not create hidden side paths.

7. PR-only integration.
   Core changes are not structurally complete until they are validated and moved through the branch/PR path defined by the constitution.

8. Goal-complete, not round-complete.
   A PR, a local fix, or one optimization round is only a milestone. The default stop condition is final objective satisfied or a real governance/safety boundary, not "this round is done".

## The Framework Layers

### 1. Constitution Layer

Primary authority:

- `JINCLAW_CONSTITUTION.md`

This layer defines the highest-level system law:

- security first
- fail closed
- brain first
- evidence over narration
- PR-only merges to `main`
- one canonical system doctor

### 2. Governance Layer

Primary files:

- `tools/openmoss/control_center/security_policy.py`
- `tools/openmoss/control_center/governance_runtime.py`
- `tools/openmoss/control_center/execution_governor.py`
- `tools/openmoss/control_center/doctor_coverage_contract.md`

This layer decides:

- what is safe
- what needs approval
- what must pause
- what counts as a governance blocker
- how new capabilities must expose health signals to the canonical doctor

### 3. Task Contract Layer

Primary files:

- `tools/openmoss/autonomy/task_contract.py`
- `tools/openmoss/autonomy/task_state.py`
- `tools/openmoss/autonomy/preflight_engine.py`

This layer defines:

- task contracts
- stage contracts
- execution policy
- retry policy
- escalation policy
- required commands, paths, and writable areas

### 4. Brain and Routing Layer

Primary files:

- `tools/openmoss/control_center/brain_router.py`
- `tools/openmoss/control_center/brain_enforcer.py`
- `tools/openmoss/control_center/response_policy_engine.py`
- `tools/openmoss/control_center/orchestrator.py`
- `tools/openmoss/control_center/mission_loop.py`

This layer decides:

- what the user means
- which task should receive the instruction
- whether to continue, re-root, branch, or reply with authoritative status
- how internal state is translated back into safe user-visible replies

### 5. Doctor, Repair, and Stability Layer

Primary files:

- `tools/openmoss/control_center/system_doctor.py`
- `tools/openmoss/control_center/jinclaw_complex_task_control_model.md`
- `tools/openmoss/control_center/jinclaw_stability_model.md`
- `tools/openmoss/autonomy/recovery_engine.py`
- `tools/openmoss/control_center/project_scheduler_policy.py`

This layer handles:

- diagnosis
- repair
- heartbeat
- incident detection
- AI takeover dispatch
- recovery prioritization
- route stability and rollback

### 6. Learning and Evolution Layer

Primary files:

- `tools/openmoss/autonomy/learning_engine.py`
- `tools/openmoss/autonomy/promotion_engine.py`
- `tools/openmoss/control_center/memory_writeback_runtime.py`
- `tools/openmoss/control_center/memory_pipeline_runtime.py`

This layer turns solved work into reusable system improvement:

- task summaries
- recurring error memory
- promoted durable runtime rules
- promoted durable doctor rules
- runtime evolution proposals

## Required Workflow Before Modifying Core Files

1. Read the constitution and this framework.
2. Identify the subsystem being changed.
3. Identify the governing files for that subsystem.
4. Check whether the change affects:
   - doctor coverage
   - routing
   - approvals
   - verification
   - recovery
   - learning
   - scheduling
5. Decide whether the change is:
   - local implementation
   - governance change
   - routing change
   - recovery change
   - doctor coverage change
   - learning/evolution change
6. Extend the canonical doctor if the new behavior introduces a new failure mode.
7. Add or preserve evidence outputs, not just behavior changes.
8. Run local validation.
9. Send the change through the branch/PR workflow.

## Required Questions Before Any Optimization

Before optimizing a core file, answer:

1. What rule or contract governs this file?
2. Does this change bypass the brain, doctor, or governance layers?
3. Does it weaken fail-closed behavior?
4. What runtime evidence will prove the optimization worked?
5. How will the canonical doctor observe success or failure?
6. What learning or reusable rule should be written if this solves a recurring problem?

If any answer is unclear, the optimization is not ready yet.

## Required Outputs For Meaningful Changes

Meaningful changes should strengthen one or more of these outputs:

- stage artifacts
- authoritative task status
- doctor incidents
- resolutions
- runtime evolution proposals
- promoted rules
- memory writebacks
- scheduler policy signals
- verification artifacts

## Required Workflow After A Problem Is Solved

When a repair or optimization resolves a real issue:

1. Verify the issue is actually resolved.
2. Record the resolution.
3. Distill the reusable rule.
4. Generate a runtime evolution proposal if the system itself should improve.
5. Feed the learning back into the doctor/runtime guidance path.

## Enforcement Intent

This framework is operational policy, not optional advice.

If a file participates in the OpenClaw/JinClaw core system and can realistically be modified during maintenance, optimization, repair, or extension, it should carry a top-of-file notice telling the modifier to read:

- `JINCLAW_CONSTITUTION.md`
- `AI_OPTIMIZATION_FRAMEWORK.md`

That notice is meant to force rules-first behavior before optimization begins.

## Machine-Readable Files

Some files must remain machine-readable and should not receive inline comment headers, including common cases such as:

- `.json`
- `.jsonl`
- `.txt`
- runtime state snapshots
- scheduler state artifacts
- control-plane registries

For those files:

1. do not break the file format by injecting comments
2. place a `RULES_FIRST_NOTICE.md` in the governing directory
3. make the checker enforce that directory-level notice
4. treat the directory notice as the rules-first anchor before editing those machine-readable files
