<!--
RULES-FIRST NOTICE:
Before modifying this file, first read:
- `JINCLAW_CONSTITUTION.md`
- `AI_OPTIMIZATION_FRAMEWORK.md`
Follow the constitution and framework:
brain-first, one-doctor, fail-closed, evidence-over-narration,
validate locally, then use the required PR workflow.
-->
# JinClaw Upstream Intake Policy

## Primary principle

JinClaw should primarily absorb **capabilities**, not blindly absorb **versions**.

That means:

- we monitor upstream OpenClaw and other borrowed OSS continuously
- we classify every meaningful update
- we selectively adopt what improves JinClaw
- we only perform real upstream version-following when the benefit clearly outweighs the integration risk

## Update classes

### 1. Must-review

These always require same-day review:

- security fixes
- auth / session / gateway protocol changes
- severe reliability bug fixes
- changes affecting Telegram / transport / runtime behavior we depend on
- release notes mentioning breaking changes

### 2. High-value capability updates

These should usually be reviewed within 24 hours:

- better orchestration patterns
- new browser / fetch / challenge handling behavior
- better observability, diagnostics, or recovery mechanisms
- improved prompt / tool / workflow logic
- support for interfaces or execution surfaces useful to JinClaw

### 3. Optional reference updates

These can be reviewed opportunistically:

- docs-only improvements
- UI polish
- workflow changes that JinClaw already supersedes
- features outside JinClaw's intended scope

## Default decision policy

### Prefer "borrow and reimplement" when:

- JinClaw already has a stronger or more specialized implementation
- upstream changes would risk breaking our brain-first orchestration
- the upstream change is mostly an architectural idea, not a low-level fix
- the capability can be localized safely into JinClaw

### Prefer "real upstream sync" when:

- a security fix is involved
- upstream fixed a deep runtime defect we still rely on
- the change affects protocols or core semantics that JinClaw cannot safely ignore
- recreating the same behavior locally would be slower or riskier than syncing

## Mandatory safeguards

No upstream adoption is considered complete until:

1. the change is classified
2. a JinClaw impact note is written
3. compatibility touchpoints are checked
4. JinClaw regression checks pass
5. brain-first routing remains active
6. degraded-mode detection remains active

## Fail-closed rule

If an upstream update causes JinClaw enhancement layers to stop participating while native OpenClaw still appears healthy, this must be treated as a failure, not a successful upgrade.

