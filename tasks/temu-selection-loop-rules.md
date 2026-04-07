# Temu Selection Loop Rules

This project must not drift into status-only updates.

## Allowed progress signals
A progress update is valid only if at least one of these exists since the prior update:
- new artifact file
- new public source note
- expanded observation/candidate set
- upgraded candidate status
- explicit blocker report that changes the plan

## Invalid progress pattern
Do not repeat “still working / still progressing” if no new artifact or blocker analysis exists.

## Stall thresholds
- 2 hours of active work with no new artifact or blocker analysis = stall
- 4 hours with no new artifact = force strategy change
- repeated stall across heartbeat cycles = report the stall clearly instead of implying progress

## Forced corrective actions on stall
Choose one:
1. change source family
2. narrow the target category
3. publish a smaller but stronger verified set
4. produce a blocker memo with the next concrete experiment

## Reporting rule
Heartbeat reports for this task must mention one of:
- new file produced
- new candidate(s) added or rejected
- blocker discovered and plan changed
If none of those happened, do not imply momentum.

## Quality rule
Prefer fewer publicly verifiable records over larger uncertain lists.

## Result-first rule
When possible, send result artifacts directly (Excel/CSV/report) instead of only summarizing activity.
