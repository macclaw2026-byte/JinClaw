# JingStack Skill System

Local-first skill scaffolding system for JinClaw.

## Goal
- replace hand-maintained `SKILL.md.tmpl` authoring with questionnaire-driven synthesis
- preserve the full lifecycle: think → plan → build → review → test → ship → reflect
- keep artifacts reproducible, removable, and free of ghost files

## Components
- `templates/questionnaire-template.json` — questionnaire schema
- `bin/render_skill_from_answers.py` — answers → `SKILL.md.tmpl` and optional `SKILL.md`
- `bin/test_jingstack_skill_system.py` — local regression test and ghost-file check
- `tests/fixtures/example-skill/answers.json` — representative fixture

## Usage
```bash
python3 tools/jingstack-skill-system/bin/render_skill_from_answers.py \
  tools/jingstack-skill-system/tests/fixtures/example-skill/answers.json \
  --output-dir /tmp/jingstack-out \
  --emit-skill-md
```

## Testing
```bash
python3 tools/jingstack-skill-system/bin/test_jingstack_skill_system.py
```
