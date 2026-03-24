# State Schema

Use this schema for a local tracking file such as `.state/github-open-source-scout.json`.

```json
{
  "lastRun": "2026-03-20T12:00:00-07:00",
  "cadence": "2d",
  "projects": [
    {
      "repo": "https://github.com/org/project",
      "name": "project",
      "firstSeen": "2026-03-20",
      "lastSeen": "2026-03-22",
      "status": "monitoring",
      "lastMeaningfulAction": "learn-from-only",
      "lastNotableUpdate": "new release",
      "beneficiarySkills": ["product-selection-engine"],
      "notes": "Useful for review clustering"
    }
  ]
}
```

## Status suggestions
- ignored
- monitoring
- learned-from
- already-integrated
- audited-rejected
- audited-approved
- installed-used

## Rule

If the state file exists, update it incrementally.
Do not overwrite useful project history just because a new run is shorter.
