# Upstream Watch

`upstream_watch` monitors OpenClaw and other borrowed open-source projects for:

- releases
- tags
- push activity
- change summaries

The goal is not to auto-upgrade JinClaw.
The goal is to ensure JinClaw learns from upstream quickly and deliberately.

## Outputs

Runtime outputs are written under:

- `tools/openmoss/runtime/upstream_watch/`

Important files:

- `upstreams.json`
- `state.json`
- `reports/latest-report.md`

## Usage

```bash
python3 /Users/mac_claw/.openclaw/workspace/tools/openmoss/upstream_watch/watch_updates.py --once
```

Optional environment variables:

- `GITHUB_TOKEN`
  - improves GitHub API rate limits

## Policy

This watcher only creates awareness and intake notes.
It does not auto-merge or auto-upgrade JinClaw.

