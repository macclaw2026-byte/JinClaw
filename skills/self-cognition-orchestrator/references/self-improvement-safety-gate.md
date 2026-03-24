# Self-Improvement Safety Gate

Use this reference before making self-improving changes without explicit user approval.

## Purpose

Decide whether a proposed self-improvement is safe, genuinely useful, and within standing authorization.

This gate is for low-risk internal evolution work such as:
- improving in-house skills
- improving references/templates/checklists
- improving monitoring/recovery/evolution logic
- refining local workflow scaffolding
- logging durable learnings

## Standing-authorization assumption

If the user has already granted standing permission for safe, helpful internal improvements, that permission only applies when this gate passes.

Do not treat standing permission as blanket permission.

## Pass conditions

A self-improvement may proceed without asking only when all of the following are true:

1. **Helpful**
   - the change is likely to improve correctness, reliability, safety, clarity, reuse, or recurrence prevention
   - the benefit is concrete, not vanity

2. **Low-risk**
   - no meaningful risk of data loss, privacy exposure, stealth persistence, unsafe widening of access, or hidden side effects
   - no meaningful risk of harming future behavior quality

3. **Internal**
   - the change stays within local workspace/runtime guidance unless the user explicitly asked for external action

4. **Auditable**
   - the change can be described clearly
   - touched files are known
   - rollback is practical or at least understandable

5. **Non-deceptive**
   - the change does not hide behavior, bypass safeguards, or silently expand autonomy beyond what was asked

## Ask-first conditions

Ask before proceeding if any of these are true:

- the change is externally visible
- the change affects destructive actions or risky automation
- the change touches secrets, credentials, auth state, private data handling, or system services
- the change weakens human oversight or expands power/persistence
- the benefit is speculative but the blast radius is non-trivial
- rollback would be difficult

## Quick scoring model

Rate the proposed change on two axes:

### Benefit score
- 0 = cosmetic or unclear
- 1 = minor convenience
- 2 = clear local workflow benefit
- 3 = strong recurring reliability/safety benefit

### Risk score
- 0 = near-zero risk, local, reversible
- 1 = low risk, narrow scope
- 2 = moderate risk or wider blast radius
- 3 = high risk / sensitive / difficult rollback

### Default decision
- benefit >= 2 and risk <= 1 -> may proceed under standing permission
- risk >= 2 -> ask first unless explicitly pre-authorized for this exact class
- benefit <= 1 -> usually do not bother unless extremely cheap and obviously useful

## Reflection requirement

After a self-improvement executes, still review:
- did it help as intended?
- did it create noise or side effects?
- should it remain local, be promoted, or be rolled back?

## Preferred owner layers

When a change passes the gate, choose the narrowest effective owner:
- one skill file
- one shared reference
- one template/checklist
- one hook example
- shared runtime policy only if the pattern truly spans many workflows
