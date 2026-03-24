# Monitoring and Retrofit Framework

Use this reference when a skill, workflow, hook, or runtime policy needs explicit monitoring coverage, missed-signal remediation, and long-term evolution.

## Purpose

Standardize how in-house skills decide:

- what should be monitored
- where hooks should live
- which monitoring mode fits the scenario
- what backstop catches missed signals
- how misses become durable improvements
- how older skills inherit the same protections

## Lifecycle hook layers

Evaluate whether the task or skill needs hooks at these layers:

1. **task-entry**
   - validate task understanding
   - confirm dependencies, scope, and safety posture

2. **skill-selection**
   - verify the chosen skill or composition is appropriate
   - detect obvious capability mismatches early

3. **stage-transition**
   - confirm a phase really completed before moving on
   - prevent silent stalls or false completion

4. **in-flight / state observation**
   - watch progress, state changes, and quality drift
   - detect low-confidence conditions while work is still recoverable

5. **tool / error**
   - detect recoverable command, edit, fetch, browser, or integration failures
   - route them into repair logic rather than stopping blindly

6. **result-validation**
   - verify the intended outcome actually happened
   - distinguish activity from success

7. **delayed backstop**
   - run a second-pass review when primary monitors can miss silently
   - catch false positives, shallow success, or incomplete closure

8. **learning / promotion**
   - convert repeated misses, good fixes, and recurring patterns into durable guidance

## Monitoring modes

Choose the monitoring mode that matches the failure mode.

### Direct state check
Use when a file, artifact, flag, or page state can be directly inspected.

### Output validation
Use when success depends on the quality or correctness of produced output.

### Stage checkpoint review
Use when multi-stage work must not silently advance past a weak or partial phase.

### Error-triggered inspection
Use when specific tool outputs or failure signatures should trigger focused recovery.

### Cross-source verification
Use when one source may be incomplete, noisy, biased, or stale.

### Time-based or delayed recheck
Use when the first pass can appear successful but later evidence may reveal a miss.

### Human confirmation
Use when impact is high, ambiguity is material, or preferences govern the right choice.

## Minimum coverage rule

For every meaningful workflow or skill run:

- define at least one **primary monitor** for each important stage or decision
- define a **backstop monitor** for fragile, high-impact, or silence-prone cases
- define a **miss-detection signal** when the primary monitor could plausibly fail without notice

If full coverage is not practical:

- name the blind spot
- define the best compensating control
- lower confidence instead of pretending coverage is complete

## Miss handling

When a monitor, hook, or validation path misses something important:

1. recover the immediate task outcome if possible
2. identify which monitor failed, was absent, or was too weak
3. decide whether the fix belongs in:
   - one skill
   - several skills
   - a shared runtime rule/reference
4. log or promote the lesson when the gap is structural or recurring

Treat monitor misses as first-class failures, not background noise.

## Retrofit policy for older skills

Do not reserve stronger monitoring only for new skills.

When older skills remain active or important:

- add stage checks where silent progression is risky
- add validation hooks where apparent success may be misleading
- add recovery hooks where failures are often repairable
- add learning hooks where repeated misses should shape future behavior

Prioritize retrofits by:

1. risk
2. frequency of use
3. recurrence of misses
4. blast radius when wrong

Prefer shared policy + small targeted edits over many divergent one-off rules.

## Suggested review questions

Before finalizing a skill or workflow, ask:

1. What can fail here without being noticed?
2. Which monitor is primary?
3. What catches a false negative?
4. What later signal would reveal shallow success?
5. If this fails, can it be repaired safely?
6. If it recurs, where should the fix become durable?
7. Which older skills should inherit the same protection?

## Minimal template

```text
Primary monitor:
Backstop monitor:
Miss-detection signal:
Remediation path:
Promotion path:
Retrofit targets:
```
