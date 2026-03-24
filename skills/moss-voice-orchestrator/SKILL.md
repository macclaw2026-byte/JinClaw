---
name: moss-voice-orchestrator
description: Integrate and operate OpenMOSS voice capabilities inside the local OpenClaw workspace, including long-form TTS, realtime TTS, and multi-speaker dialog speech, while keeping generation behind explicit tool contracts and validation hooks. Use when adding voice reply, voice report, or audio-summary features powered by MOSS-TTS or MOSS-TTSD.
---

# MOSS Voice Orchestrator

Use this skill when building OpenMOSS-derived voice capability for the current OpenClaw workspace.

This skill is inspired by:

- `OpenMOSS/MOSS-TTS`
- `OpenMOSS/MOSS-TTSD`

## Purpose

Add high-quality voice output to the workspace without polluting the main agent runtime.

The local target capability set includes:

- text-to-speech for summaries and reports
- optional realtime TTS streaming
- optional multi-speaker dialog output
- optional voice-style routing by use case

## Recommended architecture

Keep voice generation behind a tool boundary.

Preferred layers:

1. **voice request builder**
   - text normalization
   - output mode selection
   - speaker / style / language selection

2. **voice backend adapter**
   - local CLI
   - FastAPI
   - batch inference

3. **artifact manager**
   - audio output path
   - retention rules
   - metadata sidecar if needed

4. **delivery layer**
   - return file path
   - attach to chat reply if allowed
   - save summary audio to reports/output directory if requested

## Modes

Support these modes conceptually:

- `summary_tts`
- `report_tts`
- `realtime_tts`
- `dialog_tts`

## Monitoring expectations

At minimum define:

- **input-quality hook** — is the text suitable for voice output?
- **backend-health hook** — is the selected voice backend available?
- **artifact-validation hook** — was a usable audio file produced?
- **delivery-validation hook** — if sent outward, did the channel accept it?
- **fallback hook** — if TTS fails, return text cleanly instead of breaking the workflow

## Preferred rollout order

1. offline file generation for report summaries
2. optional message attachment flow
3. speaker profiles / voice presets
4. dialog mode with MOSS-TTSD
5. realtime mode only after health and latency checks are stable

## Guardrails

- text fallback must always exist
- voice generation must not block the whole task graph indefinitely
- do not silently send audio outward without the task explicitly allowing delivery
- keep generated audio discoverable and auditable
