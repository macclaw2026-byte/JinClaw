# GStack Compatibility Routing Policy

## Governing rule
JinClaw owns task routing, safety policy, runtime integrity, and promotion decisions.

## Allowed through compat
- coding subtasks
- planning for coding subtasks
- review/verification/promotion reporting
- low-risk skill scaffolding

## Forbidden through compat
- control center core logic
- fail-closed integrity logic
- self-heal root path
- secret handling and credential state
- upstream-watch authority rules
- hidden background mutation of governance files

## Fallback rule
If compat flow fails, degrades, or becomes unclear, route back to JinClaw-native flow and surface degraded status explicitly.
