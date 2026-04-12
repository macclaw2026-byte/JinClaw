<!--
RULES-FIRST NOTICE:
Before modifying this file, first read:
- `JINCLAW_CONSTITUTION.md`
- `AI_OPTIMIZATION_FRAMEWORK.md`
Follow the constitution and framework:
brain-first, one-doctor, fail-closed, evidence-over-narration,
validate locally, then use the required PR workflow.
-->
# Legacy seller-neosgo task retirement audit

Updated: 2026-04-12 04:59 PDT

## Purpose

Audit whether historical `seller-neosgo*` runtime tasks have been retired from active task space after the canonical `neosgo-seller-maintenance` workflow took over.

## Canonical replacement

Active canonical workflow:
- `neosgo-seller-maintenance`
- Documentation: `/Users/mac_claw/.openclaw/workspace/projects/neosgo-seller-maintenance/README.md`
- Latest state: `/Users/mac_claw/.openclaw/workspace/data/neosgo-seller-maintenance-state.json`

## Audit result

Legacy `seller-neosgo*` tasks are **not yet fully retired from active task space**.

### Still active / non-retired task-status records

| task status file | status | current_stage | next_action | note |
|---|---|---:|---|---|
| seller-neosgo.json | planning | plan | start_stage:plan | stale legacy root task still looks active |
| seller-neosgo-followup-followup.json | running | execute | execute_stage:execute | stale legacy descendant still marked running |
| seller-neosgo-followup-12.json | waiting_external | understand | poll_run:61249567c6be4449b49236e560b32648 | unresolved external wait |
| seller-neosgo-followup-13.json | blocked | execute | bind_session_link | unresolved blocked handoff |
| seller-neosgo-followup-14.json | verifying |  | verify_done_definition | unresolved verification tail |
| seller-neosgo-followup-2.json | planning | plan | start_stage:plan | stale planning artifact |
| seller-neosgo-followup-3.json | waiting_external | understand | poll_run:599d35767fc34321bf97d65e923006fa | unresolved external wait |
| seller-neosgo-followup-4.json | planning | plan | start_stage:plan | stale planning artifact |
| seller-neosgo-followup-5.json | planning | execute | start_stage:execute | stale execution artifact |
| seller-neosgo-followup-6.json | blocked | execute | bind_session_link | unresolved blocked handoff |
| seller-neosgo-followup-9.json | recovering | execute | repair_verification_failure | unresolved recovery artifact |

### Legacy task-status records with business outcome confirmed but stale active status

| task status file | recorded status | authoritative summary |
|---|---|---|
| seller-neosgo-followup-10.json | planning | says task is completed; stale overview state only |

### Already clean / terminal

| task status file | status |
|---|---|
| seller-neosgo-followup.json | completed |
| seller-neosgo-followup-8.json | completed |
| seller-neosgo-followup-11.json | completed |

## Implication for done definition

Current done definition item:
- `legacy seller-neosgo followup tasks are retired from active task space`

Result:
- **Not yet satisfied**

## Recommended cleanup action

The runtime/control-center layer should archive, retire, or otherwise neutralize the above stale `seller-neosgo*` active task-status records so only the canonical `neosgo-seller-maintenance` lane remains active.

A minimum acceptable cleanup is:
1. convert stale planning/running/waiting/blocking legacy records into terminal retired/completed metadata, or
2. move them out of active task-status space into an archive namespace, and
3. keep this audit file as the operator-facing reference that explains the canonical replacement.

## Evidence sources

- `/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/control_center/task_status/seller-neosgo*.json`
- `/Users/mac_claw/.openclaw/workspace/tools/openmoss/runtime/control_center/task_status/neosgo-seller-maintenance.json`
- `/Users/mac_claw/.openclaw/workspace/data/neosgo-seller-maintenance-state.json`
