---
name: example-lifecycle-skill
description: |
  Create a structured local skill from questionnaire answers while preserving the full think to reflect lifecycle. Use when:
  - Use when a new in-house skill should be scaffolded from a questionnaire instead of hand-writing the tmpl file.
  - Use when the operator wants deterministic questionnaire to tmpl generation with lifecycle preservation.
---
<!-- AUTO-GENERATED from questionnaire answers via JingStack skill system. -->

# Example Lifecycle Skill

## Trigger Phrases
- create a new skill from answers
- generate tmpl from questionnaire
- preserve full lifecycle in the new skill

## Jobs To Be Done
- turn answered questions into a valid SKILL.md.tmpl source file
- carry the tmpl forward into deterministic skill generation
- keep think, plan, build, review, test, ship, and reflect explicit

## Inputs
- questionnaire answers json
- optional local notes about scripts and references

## Outputs
- SKILL.md.tmpl
- generated SKILL.md
- skeleton resource directories when requested

## Resource Plan
### scripts
- render_skill_from_answers.py

### references
- questionnaire-template.json

### assets
- none specified

## Constraints
- stay local-first
- avoid ghost files
- make generated artifacts reproducible and removable

## Lifecycle

Preserve the full lifecycle below as first-class workflow stages.

- Do not collapse the lifecycle into a shorter loop.
- Allow light local adaptation but keep all lifecycle stages visible.

### think
- run the think stage explicitly
- record outputs for think
- do not silently skip think

### plan
- run the plan stage explicitly
- record outputs for plan
- do not silently skip plan

### build
- run the build stage explicitly
- record outputs for build
- do not silently skip build

### review
- run the review stage explicitly
- record outputs for review
- do not silently skip review

### test
- run the test stage explicitly
- record outputs for test
- do not silently skip test

### ship
- run the ship stage explicitly
- record outputs for ship
- do not silently skip ship

### reflect
- run the reflect stage explicitly
- record outputs for reflect
- do not silently skip reflect


## Testing
### checks
- validate questionnaire structure
- render deterministic tmpl output
- generate final SKILL.md
- verify lifecycle sections are present

### evidence
- fixture answers file
- rendered tmpl file
- generated markdown file
- test report

## Host Notes
- Keep JinClaw as control plane.
- Use compat adapters rather than replacing local governance.

## Generation Notes
- This tmpl was synthesized from questionnaire answers.
- Regenerate from answers instead of hand-editing when possible.
