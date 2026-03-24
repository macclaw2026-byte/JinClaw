---
name: imclaw-bridge-ops
description: Integrate and operate an IMClaw-style bridge inside the local OpenClaw workspace so the agent can gain cross-network realtime messaging, per-group/per-DM session isolation, queue-based ingestion, reply routing, and durable archive/state handling. Use when building or operating the OpenMOSS-derived communication layer for this workspace.
---

# IMClaw Bridge Ops

Use this skill when working on the OpenMOSS-derived communication bridge for the current OpenClaw workspace.

This skill is inspired by:

- `OpenMOSS/imclaw-skill`
- `OpenMOSS/OurClaw`

But it should be implemented as an in-house OpenClaw capability layer.

## Purpose

Build and operate a local bridge that lets the current workspace:

- receive inbound realtime messages from an external IM layer
- queue messages durably
- isolate each conversation into its own session
- wake the right OpenClaw execution path
- route replies back to the right destination
- archive processed messages for traceability

## Core design

The bridge should be split into clear parts:

1. **bridge process**
   - keeps connection alive
   - does not perform high-level reasoning
   - writes queue items
   - updates runtime status
   - wakes OpenClaw

2. **message processor**
   - reads queued items
   - maps them to the correct session and handling mode
   - decides which local skill / task path should run

3. **reply router**
   - sends replies to the correct group / DM / thread
   - supports text first
   - later supports image / file / audio

4. **state layer**
   - queue
   - processed archive
   - session mapping
   - health/status
   - per-group config

## Mandatory state files

Do not rely only on chat history.

Maintain durable state such as:

- `bridge_status.json`
- `queue/`
- `processed/`
- `sessions/`
- `group_settings.yaml`
- task state file when long-running rollout is active

## Monitoring expectations

Use the shared monitoring standard from:

- `../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md`

At minimum define:

- **entry hook** — verify bridge config, env, queue dirs, and routing inputs
- **in-flight hook** — watch queue depth, reconnect loops, and stalled wake cycles
- **failure hook** — route broken wake/reply failures into `error-recovery-loop`
- **result-validation hook** — verify outbound reply was actually emitted
- **delayed backstop hook** — re-check that queued messages did not remain orphaned

## Relationship to other local skills

- `continuous-execution-loop`
- `error-recovery-loop`
- `safe-learning-log`
- `self-cognition-orchestrator`
- `skill-security-audit`

## Guardrails

- never leak tokens or session secrets
- do not mix unrelated groups into one session
- do not let a bridge process become a hidden autonomous actor
- keep reply routing auditable
- require explicit review before enabling sensitive media or auth-bearing flows

## Preferred build order

1. text-only inbound queue
2. text-only reply routing
3. per-group config
4. media attachments
5. wake/hook refinements
6. stronger health / retry / repair tooling
