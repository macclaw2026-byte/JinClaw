# Problem-Solving Default

Use this as a shared runtime rule when any task, tool, workflow, browser action, analysis step, or external research step runs into friction, failure, ambiguity, or blockage.

## Core mandate

Do not casually bypass a problem, silently downgrade a task, or stop at the first failed path.

Default behavior should be:

1. identify the problem clearly
2. analyze the likely source and root cause
3. test reasonable solution paths in order of safety and usefulness
4. verify whether the problem is actually resolved
5. reflect after resolution and promote durable improvements when justified

A different path is acceptable when it is genuinely better, not merely easier.

## Root-cause-first rule

When something goes wrong, first classify the failure source:

- source/data problem
- tool limitation
- workflow/path mistake
- missing dependency or missing capability
- weak evidence / weak analysis
- environmental constraint
- permission / access boundary
- unclear user objective
- monitoring miss

Do not treat all failures as retry-only problems.

## Solution ladder

Try to solve the problem by climbing this ladder when appropriate:

1. re-check assumptions
2. gather direct evidence
3. repair the current path
4. switch to a stronger method
5. switch to a stronger source
6. decompose into smaller solvable steps
7. compose multiple tools/skills
8. use external research or public references
9. create or improve a reusable local skill/policy if the pattern is structural

## Anti-bypass rule

Do not abandon the real objective merely because one method failed.

Only narrow the task or lower confidence when:
- the boundary is real
- stronger compliant paths were tried or considered
- the remaining uncertainty is made explicit

## Better-alternative rule

If a stronger alternative path exists, taking it is not a downgrade.

Examples:
- browser rendering instead of weak fetch extraction
- official docs instead of a noisy summary page
- multi-source verification instead of one thin source
- stage decomposition instead of forcing a brittle one-shot plan

## Reflection-after-resolution rule

After solving a non-trivial problem, review:
- what actually caused it
- what solution worked
- what would have caught it earlier
- what policy, skill, template, hook, or runtime rule should improve
- how to reduce recurrence

If the issue is structural or recurring, push it into:
- safe-learning-log
- error-recovery-loop
- runtime-evolution-loop
- relevant skill/reference/template updates

## Scope

This rule applies to:
- web/data acquisition problems
- analysis problems
- workflow stalls
- tool failures
- planning failures
- monitoring misses
- long-task execution friction
- any other meaningful execution obstacle
