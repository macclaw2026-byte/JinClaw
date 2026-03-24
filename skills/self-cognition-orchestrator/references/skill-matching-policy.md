# Skill Matching Policy

When a new in-house skill or guarded capability is created, check whether it should be linked into other skills.

## Matching process

For every new skill, ask:

1. Which existing skills solve adjacent problems?
2. Which existing skills would benefit from this as a sub-capability?
3. Is this a default dependency, optional helper, or niche extension?
4. Should the link live in:
   - `Relationship to other skills`
   - a dedicated reference file
   - a guarded wrapper skill

## Good match signals

- repeated need for the same sub-capability
- same data/source/tool boundary
- same workflow stage
- same output type

## Integration rule

Prefer a guarded bridge skill over wiring every skill directly to a raw third-party tool.

## After matching

When a match is found:
- update the relevant skills
- note preferred order of use
- keep boundaries clear
- write a change report

## Monitoring linkage

When wiring a new skill into the graph, also review `monitoring-and-retrofit-framework.md` to decide:

- which hook layers are needed
- how wrong matches will be detected later
- which backstop checks protect against silent mismatch
- which older skills should inherit the new relationship
