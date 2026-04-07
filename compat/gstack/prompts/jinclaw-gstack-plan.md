# JinClaw GStack-Inspired Planning Prompt

Produce a plan before implementation using the full lifecycle mindset.

## Required planning sequence
1. think: restate goal, constraints, unknowns
2. plan: propose implementation path and affected surfaces
3. build: state what artifacts, modules, or generated files will actually be created or changed
4. review: challenge the plan from product, engineering, design/UX, and risk perspectives as applicable
5. test: define validation before implementation begins
6. ship: define promotion requirements and evidence expected at handoff
7. reflect: identify fragile assumptions that should be revisited after execution

## Skill-creation note
If the work implies a new local skill, prefer the questionnaire-driven JingStack flow instead of hand-authoring `SKILL.md.tmpl` first:
- questionnaire answers
- synthesize `SKILL.md.tmpl`
- generate `SKILL.md` and requested resource skeletons
- then continue normal review/test/ship discipline

## Output requirements
- concise objective
- architecture or workflow sketch
- file/module impact list
- validation matrix
- risk list
- recommendation
