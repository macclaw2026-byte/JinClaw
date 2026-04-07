# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.


### Data Harvesting

- Crawl4AI local wrapper: `~/\.openclaw/workspace/tools/bin/crawl4ai`
- Crawl4AI venv: `~/\.openclaw/workspace/tools/crawl4ai-venv`
- Setup completed with browser downloads and doctor health check passing on 2026-03-20.

### Process Monitoring

- Current process snapshot: `~/.openclaw/workspace/tools/bin/procs-now`
- Live focused process watch: `~/.openclaw/workspace/tools/bin/procs-watch` (default refresh every 3s; pass seconds as arg)
