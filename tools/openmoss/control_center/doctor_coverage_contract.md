<!--
RULES-FIRST NOTICE:
Before modifying this file, first read:
- `JINCLAW_CONSTITUTION.md`
- `AI_OPTIMIZATION_FRAMEWORK.md`
Follow the constitution and framework:
brain-first, one-doctor, fail-closed, evidence-over-narration,
validate locally, then use the required PR workflow.
-->
# Doctor Coverage Contract

## Purpose

This contract defines how JinClaw keeps exactly one canonical whole-system doctor while still allowing the system to grow.

The rule is simple:
- JinClaw has one doctor and only one doctor
- new system coverage must extend that doctor
- coverage gaps must be surfaced as explicit contract misses, not solved by creating another doctor

## Canonical ownership

The single canonical doctor path is:
- diagnosis authority: `tools/openmoss/control_center/system_doctor.py`
- aggregated doctor health payload: `tools/openmoss/ops/jinclaw_ops.py`

Operational rule:
- explicit operator doctor entrypoints such as `jinclaw-doctor` must refresh the canonical doctor result before presenting the aggregated payload; they may not silently rely on structurally stale cache data as the final authority

Governance anchors:
- `JINCLAW_CONSTITUTION.md`
- `tools/openmoss/control_center/README.md`

## Coverage rule for all future changes

When adding any of the following:
- file
- feature
- skill
- module
- bridge
- scheduler
- execution path
- verification path
- recovery path
- message path

The author must decide one of these outcomes:

1. **Direct doctor coverage added**
   - the new component is checked directly by the canonical doctor path

2. **Signal exported to doctor path**
   - the new component emits a signal, artifact, or summary that the canonical doctor consumes

3. **Explicit temporary blind spot declared**
   - coverage is not yet direct, but the change records:
     - what is not yet covered
     - what backstop compensates for it
     - what future retrofit should close the gap

Outcome 3 is temporary and should not become the default.

## Prohibited pattern

Do not do any of the following:
- create a second doctor for a subsystem
- create a subsystem-specific peer doctor entrypoint as an authority
- create doctor-to-doctor coordination as a required health path
- hide a coverage gap by inventing a new doctor label

## Required review questions for any new subsystem or major change

Before a change is considered structurally complete, answer:

1. How does the canonical doctor observe this change?
2. If it cannot observe it directly, what exported signal reaches the doctor?
3. What is the primary monitor?
4. What is the backstop monitor?
5. What delayed signal would reveal shallow success?
6. Is any blind spot still present?
7. If yes, where is the retrofit owner?

## Minimal coverage template

```text
Component:
Direct coverage path:
Exported signal/artifact:
Primary monitor:
Backstop monitor:
Delayed verification:
Blind spot:
Retrofit owner:
```

## Best placement in the architecture

This contract belongs in the control-center layer because the control center is the only layer with whole-system visibility across:
- planning
- routing
- autonomy execution
- session/message health
- scheduler integrity
- result validation
- recovery and delayed backstop checks

## Operational expectation

Any future optimization should treat doctor coverage as part of the definition of done.
If a new capability lands without doctor coverage, the work is incomplete until the canonical doctor path can track it or an explicit temporary blind-spot contract is written.
