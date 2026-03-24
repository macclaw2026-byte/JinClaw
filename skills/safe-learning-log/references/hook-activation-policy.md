# Hook Activation Policy

Use this policy before moving any hook from example/reference status into real default usage.

Apply the shared monitoring standard from `../../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md` and the security gate from `../../skill-security-audit/SKILL.md`.

## Default posture

- example hooks are **not** enabled by default
- promotion from example -> active usage requires a narrow trigger, clear side effects, and an audit trail
- if uncertain, keep the hook as documentation/example rather than auto-running behavior

## Activation classes

### Class A — reminder hooks
Examples:
- prompt-round reminder
- post-tool review reminder
- delayed review reminder

Requirements:
- local only
- no network calls
- no secret access
- no automatic edits
- low spam risk

### Class B — diagnostic/recovery hooks
Examples:
- post-error recovery prompts
- delayed backstop triggers

Requirements:
- local only
- no destructive action
- no automatic high-impact edits
- explicit verification step
- noise control so repeated failures do not spam the user

### Class C — high-sensitivity hooks
Examples:
- hooks that edit durable instruction files automatically
- hooks that install dependencies
- hooks that touch secrets, browser auth state, or system services
- hooks that persist in the background

Policy:
- do not enable by default
- require explicit review under `skill-security-audit`
- prefer safer manual or semi-manual alternatives

## Activation checklist

Before enabling any hook, answer:

1. What exact trigger causes it to run?
2. What is the primary monitor it supports?
3. What backstop verifies it did not create noise or false confidence?
4. Does it write files? If yes, which files?
5. Could it leak data, trigger secrets exposure, or widen system access?
6. Is there a simpler non-hook alternative?
7. If it misfires, how is it rolled back?

## Default decisions for current example hooks

- `post-tool-error-recovery.sh` -> eligible for selective Class B use
- `post-tool-review.sh` -> eligible for selective Class A use
- `delayed-backstop-review.sh` -> keep as opt-in Class B until a strong delayed trigger exists
- `post-run-selection-learning.sh` -> keep domain-specific and opt-in
- `user-prompt-reminder.sh` -> eligible for selective Class A use after wording stays concise and low-noise

## Rollout rule

Enable hooks gradually:

1. example only
2. opt-in for one workflow/skill
3. observe noise, value, and misses
4. expand only if the hook is consistently helpful and auditable
