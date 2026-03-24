# JinClaw Security Policy

## Scope

This repository contains the source assets for JinClaw. It must not become a container for sensitive local state.

## Never Commit

- passwords
- API keys
- OAuth tokens
- browser session data
- cookies
- auth headers
- `.env.local` or similar private files
- personal memory state
- runtime outputs containing sensitive user or business data

## External Tool Rules

JinClaw may interact with external OSS, tools, and public sources, but:

- direct adoption must be reviewed
- high-risk actions require approval
- adoption should be auditable and reversible
- if direct adoption is unsafe, JinClaw should prefer local reconstruction of the useful capability

## Runtime Guardrail

JinClaw must not silently degrade into a weaker mode if critical enhancement layers are inactive. Health checks should surface degraded operation explicitly.

## Reporting

If a sensitive file is accidentally committed locally:

1. Stop and avoid pushing.
2. Remove the file from tracking.
3. Rotate the exposed secret if applicable.
4. Verify `.gitignore` coverage before proceeding.

If a secret has already been pushed remotely, treat it as compromised and rotate it immediately.
