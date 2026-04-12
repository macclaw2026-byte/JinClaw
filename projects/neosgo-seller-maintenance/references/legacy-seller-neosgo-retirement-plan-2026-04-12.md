<!--
RULES-FIRST NOTICE:
Before modifying this file, first read:
- `JINCLAW_CONSTITUTION.md`
- `AI_OPTIMIZATION_FRAMEWORK.md`
Follow the constitution and framework:
brain-first, one-doctor, fail-closed, evidence-over-narration,
validate locally, then use the required PR workflow.
-->
# Legacy seller-neosgo retirement plan

Updated: 2026-04-12 05:17 PDT

## Goal

Retire historical `seller-neosgo*` followup artifacts from active task space so `neosgo-seller-maintenance` is the only active canonical seller-maintenance lane.

## What is currently active

The current active residue is concentrated in:

- `tools/openmoss/runtime/control_center/task_status/seller-neosgo*.json`

No matching active task directories were found under:

- `tools/openmoss/runtime/autonomy/tasks/`

This means the remaining blocker is primarily **control-center status residue**, not a live business workflow that still owns the canonical NEOSGO seller maintenance job.

## Retirement strategy

### Phase 1 — classify each legacy status record

1. **terminal-completed but stale status text**
   - example: `seller-neosgo-followup-10.json`
   - authoritative summary already says completed
   - action: normalize status metadata to terminal retired/completed state

2. **stale planning / blocked / waiting / recovering residue without active task directory**
   - examples:
     - `seller-neosgo.json`
     - `seller-neosgo-followup-followup.json`
     - `seller-neosgo-followup-12.json`
     - `seller-neosgo-followup-13.json`
     - `seller-neosgo-followup-14.json`
     - `seller-neosgo-followup-2/3/4/5/6/9.json`
   - action: archive or rewrite out of active state

3. **already terminal**
   - examples:
     - `seller-neosgo-followup.json`
     - `seller-neosgo-followup-8.json`
     - `seller-neosgo-followup-11.json`
   - action: leave as historical evidence or move to archive later

### Phase 2 — preferred technical cleanup

Preferred cleanup order:

1. snapshot all current `seller-neosgo*.json` files into an archive folder
2. rewrite active control-center records to a terminal state such as `completed` or `retired`
3. set `next_action` to `none`
4. add a note pointing to `neosgo-seller-maintenance` as canonical replacement
5. if the runtime supports archive namespaces, move legacy records out of `task_status/`

### Phase 3 — verify done definition impact

After cleanup, verify:

- `projects/neosgo-seller-maintenance/README.md` still points to this retirement plan and the audit file
- `data/neosgo-seller-maintenance-state.json` still shows the daily workflow is runnable and producing artifacts
- no non-terminal `seller-neosgo*.json` files remain in `control_center/task_status/`

## Verification commands used to build this plan

- enumerate current legacy status files in `control_center/task_status/`
- confirm there are no matching active task directories in `runtime/autonomy/tasks/`

## Resulting assessment

The canonical workflow is already documented and runnable.
The remaining done-definition gap is a **metadata retirement / control-center hygiene** task.
