# JinClaw Governance

JinClaw is no longer treated as a thin patch on top of OpenClaw.

It is managed as:

- `upstream knowledge sources`: open-source projects we monitor and selectively learn from
- `JinClaw core`: our own orchestration, autonomy, bridge, safety, and recovery layers
- `compatibility surface`: the small set of touchpoints where JinClaw interacts with upstream OpenClaw behavior

The default policy is:

- do **not** automatically follow every upstream OpenClaw release
- do **not** patch upstream dist output unless truly unavoidable
- do selectively absorb ideas, fixes, and mechanisms from upstream and related OSS
- do maintain a recoverable Git history for JinClaw itself
- do fail closed when JinClaw enhancement layers are degraded or disconnected

See:

- `../../JINCLAW_CONSTITUTION.md`
- `../../CONTRIBUTING.md`
- `../../SECURITY.md`
- `jinclaw-upstream-intake-policy.md`
- `jinclaw-repository-plan.md`
- `jinclaw-live-guardrails.md`
