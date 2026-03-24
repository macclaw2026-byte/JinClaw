# Self Cognition Orchestrator Decision Table

Use this together with `monitoring-and-retrofit-framework.md` so planning includes hook layers, backstops, and retrofit implications rather than just route choice.

## Core sequence

1. Understand the prompt
2. Resolve ambiguity from context
3. Look for a better path to the same goal
4. Decide whether a skill is needed
5. Check local skills first
6. Search external sources if needed
7. Audit before install
8. Prefer replacement over risky installation
9. Create an in-house skill if needed
10. Execute
11. Trigger safe-learning-log

## When to use a skill

Use a skill when:
- the workflow is specialized
- reuse is likely
- reliability matters
- there is existing skill coverage

Do not use a skill when:
- direct execution is simpler
- the task is one-off and trivial
- skill overhead exceeds benefit

## External skill search logic

### Sources
- local existing skills first
- external skills ecosystem via find-skills logic
- ClawHub as an additional source

### Selection preference
- readable source
- clear provenance
- narrow scope
- low-risk behavior

## Installation policy

- A -> install allowed
- B -> prefer safer replacement
- C -> do not install

## Creation policy

Create a new in-house skill when:
- no good safe skill exists
- the task is recurring
- the workflow is stable enough to capture

## Planning control questions

For every meaningful plan ask:
- what primary monitor supports this path?
- what backstop catches a wrong route?
- what later signal would reveal shallow success?
- if this path fails repeatedly, which older skills should inherit the fix?
