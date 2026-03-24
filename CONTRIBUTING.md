# Contributing to JinClaw

JinClaw uses a guarded workflow. Do not treat this repository like a casual scratchpad.

## Branching

- Branch from `main`
- Use a short descriptive branch name
- Do not push directly to `main`

Suggested patterns:

- `feat/<topic>`
- `fix/<topic>`
- `ops/<topic>`
- `governance/<topic>`

## Merge Policy

- All changes must land through Pull Requests
- Use `Squash and merge`
- Do not merge if required checks are failing

## Before Opening a PR

Run the most relevant checks locally:

```bash
/Users/mac_claw/.openclaw/workspace/tools/bin/jinclaw-status
/Users/mac_claw/.openclaw/workspace/tools/bin/jinclaw-doctor
/Users/mac_claw/.openclaw/workspace/tools/bin/jinclaw-upgrade-check
```

Also run targeted validation for the area you changed, such as:

- autonomy runtime smoke test
- control center mission cycle smoke test
- preflight or recovery path verification
- launchd/runtime wiring verification for live-service changes

## Sensitive Data Rules

Never commit:

- secrets, passwords, tokens, cookies, auth headers
- `.env.local`, private overrides, or personal config values
- browser profiles or user-data state
- runtime caches, runtime outputs, or memory state
- local datasets that are not intended for source control

If you need a config example, commit a template instead.

## Upstream Intake Rules

Do not automatically copy upstream OpenClaw changes into JinClaw.

Instead:

- monitor upstream
- classify the update
- decide whether to ignore, borrow ideas, or intentionally adopt a fix
- document the reasoning in the PR

## PR Expectations

A PR should explain:

- what changed
- why this change is needed
- what was validated
- whether live runtime behavior is affected
- whether any upstream behavior or OSS idea was borrowed

## Operational Safety

For changes touching any of the following:

- `tools/openmoss/autonomy`
- `tools/openmoss/control_center`
- `tools/openmoss/ops`
- `.github/workflows`

you should assume the change is system-sensitive and validate accordingly.
