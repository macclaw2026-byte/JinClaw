# JinClaw

JinClaw is a customized, brain-first evolution of OpenClaw built around a control center, autonomy runtime, safety-first execution, and selective upstream intake.

This repository tracks the reproducible JinClaw workspace:

- source code
- skills
- governance docs
- tooling
- tests and project docs

It intentionally does not track local secrets, runtime state, caches, personal memory, or large local environments.

## GStack-inspired compatibility layer

JinClaw now includes a JinClaw-owned `compat/gstack/` layer for selectively absorbing high-value Jin-gstack mechanisms without giving up JinClaw control, governance, or runtime authority.

Current integrated pieces:
- lifecycle discipline preserved in full: think -> plan -> build -> review -> test -> ship -> reflect
- compat routing and intake policy docs
- JinClaw-owned ACP prompt variants inspired by gstack-lite/planning discipline
- automated skill factory for questionnaire -> `SKILL.md.tmpl` -> `SKILL.md` generation
- skill doctor checks and tests

## Automated skill generation

Use the skill factory to create a new JinClaw skill scaffold from a structured questionnaire:

```bash
tools/bin/jinclaw-skill-factory
```

Or feed answers from a file:

```bash
tools/bin/jinclaw-skill-factory --answers path/to/answers.json
```

Generated output lands under `skills/<skill-name>/` and includes:
- `SKILL.md.tmpl`
- `SKILL.md`
- optional `references/`
- optional `scripts/`
- optional `assets/`
- `skill-factory-manifest.json`

Validate generated skills with:

```bash
tools/bin/jinclaw-skill-doctor
```
