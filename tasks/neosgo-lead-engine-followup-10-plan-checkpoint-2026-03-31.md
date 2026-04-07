# Neosgo lead-engine followup-10 plan checkpoint (2026-03-31 18:19 PDT)

## Planning objective
Compare multiple safe execution plans for the overnight no-progress symptom, then select the best path that resolves the actual blocker without weakening local security boundaries.

## Confirmed problem statement
The symptom is not an unfinished Downloads → ZIP → DuckDB → lead-engine business pipeline.
The confirmed issue is stale orchestration/supervision state causing false "still launching / still in progress" interpretation and likely repeated requeue behavior.

## Candidate plans considered

### Plan A — Re-run the full import and downstream lead-engine pipeline
**What it would do**
- rediscover archives in `~/Downloads/US Business Data`
- re-import into DuckDB
- rebuild normalized/scored/outreach tables

**Pros**
- brute-force confidence if the pipeline were actually corrupted

**Cons**
- expensive and unnecessary given verified parity and downstream outputs
- risks wasted machine time and more confusion in progress signals
- does not address the proven root cause in supervision/runtime state

**Verdict**
Reject.

### Plan B — Only verify a single happy-path chain again
**What it would do**
- spot-check one archive/member or one downstream output
- report that one path works

**Pros**
- low cost

**Cons**
- specifically fails Jacken's request
- would miss orchestration-state residue and repeated requeue behavior
- does not solve the overnight no-progress symptom

**Verdict**
Reject.

### Plan C — Correct stale state and add explicit anti-requeue guard based on existing completion artifacts
**What it would do**
- trust already verified final-state and runtime-handoff artifacts
- normalize stale progress/daemon signals to completed
- document that future orchestration should short-circuit when final-state + handoff already say done

**Pros**
- directly addresses the real blocker
- preserves local security boundaries
- minimal write surface, no unnecessary reruns
- aligns with observed evidence: no active workers, completed imports, completed downstream outputs

**Cons**
- depends on locating every place that still keys off stale status files

**Verdict**
Best current plan.

### Plan D — Patch scheduler/runtime code immediately before mapping all references
**What it would do**
- make speculative code edits to requeue logic right away

**Pros**
- potentially eliminates recurrence at source

**Cons**
- premature before full reference mapping
- higher risk of editing the wrong control point
- unnecessary for plan-stage selection

**Verdict**
Defer until execute stage after reference mapping.

## Selected plan
**Plan C — Correct stale state and use existing completion artifacts as the authoritative stop condition**

## Why this is the best approved path
1. It matches the proven root cause.
2. It resolves the apparent stall without rerunning a massive completed data pipeline.
3. It stays fully inside safe local boundaries.
4. It creates a clean bridge into execute-stage work: locate the exact requeue decision point and make it honor final-state/handoff guards.

## Concrete actions already aligned with the selected plan
- updated `tmp/lead-import-daemon-status.json` from stale `launching-runner` residue to `completed/done`
- recorded root cause and evidence in dedicated checkpoint/output files

## Execute-stage plan
1. map references to stale progress/daemon/final-state signals in workspace code and task files
2. identify the specific branch that still requeues or reinterprets followup-10 as active
3. patch the local decision logic so `final_state=completed` and `runtime_handoff=done` short-circuit repeat execution
4. specifically fix control-center authoritative state fusion so completed seller/business evidence can override stale `planning/understand` and `blocked/bind_session_link` records
5. verify no active process is restarted, no brain receipt keeps publishing stale authoritative summaries, and no local state regresses to pseudo-running
6. write final checkpoint with proof

## Additional plan-stage evidence discovered after initial selection
The stale-state problem is broader than the daemon/progress sentinel alone.

Authoritative runtime records still disagree with verified business evidence:
- `tools/openmoss/runtime/control_center/task_status/neosgo-lead-engine-followup-10.json`
  - still says `status=planning`, `current_stage=understand`, `next_action=start_stage:understand`
- `tools/openmoss/runtime/control_center/cache/stage_context/neosgo-lead-engine-followup-10-understand.json`
  - still says `status=waiting_external`, `next_action=poll_run:...`
- `tools/openmoss/runtime/control_center/task_status/seller-neosgo-followup-10.json`
  - still says `status=blocked`, `next_action=bind_session_link`
- `tools/openmoss/runtime/control_center/brain_receipts/openclaw-main/main.json`
  - has already delivered the stale authoritative summary back into the main session

This means the best plan remains Plan C, but its true repair target is now clearer:
**the control-center authoritative status synthesis / state-merging layer must honor existing completion proof and final-state guards before emitting new authoritative task summaries or successor work.**

## Security check
- no external writes required
- no credentials or cookies required
- no host security boundary changes required
- no destructive deletion planned
