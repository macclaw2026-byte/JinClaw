# Marketing Automation Suite

This directory provides the shared engineering layer for the reusable marketing skill system:

1. `prospect-data-engine`
2. `marketing-strategy-engine`
3. `outreach-feedback-engine`

## What lives here

- `architecture.md`
- `interfaces.md`
- `task-lifecycle.md`
- `project-config-template.yaml`
- `project-config-template.json`
- `schemas/`
- `scripts/`

## Shared engineering entrypoints

### Initialize a new project workspace

```bash
python3 scripts/init_marketing_project.py \
  --project-root /Users/mac_claw/.openclaw/workspace/projects/my-growth-project \
  --project-id my-growth-project
```

### Validate a project config

```bash
python3 scripts/validate_project_config.py \
  --config /Users/mac_claw/.openclaw/workspace/projects/my-growth-project/config/project-config.json
```

### Run one unified suite cycle

```bash
python3 scripts/run_marketing_suite_cycle.py \
  --project-root /Users/mac_claw/.openclaw/workspace/projects/my-growth-project
```

## Design principle

Keep the suite reusable across projects by only swapping:

- project goal
- product/service type
- ICP
- priority channels
- conversion target

Do not bake brand-specific logic into the shared layer.
