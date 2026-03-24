# JinClaw Repository Plan

## GitHub repository

Remote:

- `git@github.com:macclaw2026-byte/JinClaw.git`

## Recommended repository structure

The repository should track JinClaw's own logic and governance, not mirror Homebrew-installed OpenClaw wholesale.

Recommended top-level layout:

- `docs/`
  - architecture, policies, upgrade notes, intake reports
- `jinclaw/`
  - JinClaw-owned code and scripts
- `compat/`
  - adapters for upstream OpenClaw touchpoints
- `monitoring/`
  - upstream-watch tooling and generated reports
- `tests/`
  - JinClaw regression, doctor, upgrade checks
- `patches/`
  - only unavoidable upstream patch manifests
- `references/`
  - curated notes about borrowed open-source capabilities

## What should remain outside the repo

- Homebrew-installed OpenClaw dist output in `/opt/homebrew/lib/node_modules/openclaw`
- large runtime state under `~/.openclaw/runtime`
- local secrets or tokens
- browser profiles and session state

## Source-of-truth rule

JinClaw's source of truth is the Git repository, not the installed OpenClaw package and not ad-hoc local patches.

## Rollback rule

Every meaningful JinClaw change should remain roll-backable via Git history, not by reconstructing local state manually.

