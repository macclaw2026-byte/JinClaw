# NEOSGO Marketing Suite

Projectized instance of the reusable three-skill marketing automation system for `neosgo.com`.

Operating stance:
- trade-focused website growth
- priority accounts: designers, contractors/builders, electricians, distributors/showrooms/dealers
- priority regions: New England first, then NY / CA / TX / FL
- execution bias: form + LinkedIn first
- outbound email currently disabled in routing because sender reputation needs rebuilding

Key folders:
- `config/`: project configuration
- `data/`: seeds, raw imports, discovery targets, discovery queries
- `output/`: cycle artifacts
- `runtime/`: rolling state and strategy weights
- `reports/`: per-cycle reports

Useful operational commands:
- Run one full cycle:
  `python3 /Users/mac_claw/.openclaw/workspace/skills/marketing-automation-suite/scripts/run_marketing_suite_cycle.py --project-root /Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite`
- Build a feedback template from the latest execution queue:
  `python3 /Users/mac_claw/.openclaw/workspace/skills/outreach-feedback-engine/scripts/build_feedback_event_template.py --execution-queue /Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite/output/marketing-automation-suite/<cycle_id>/execution-queue.json --output /Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite/data/feedback-events.template.json`
- Merge completed operator feedback rows back into the live feedback file:
  `python3 /Users/mac_claw/.openclaw/workspace/skills/outreach-feedback-engine/scripts/merge_feedback_events.py --source /Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite/data/feedback-events.template.json --target /Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite/data/feedback-events.json --archive /Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite/data/feedback-events.template.archive.json`
- Check whether the current repo state is safe for a scoped PR:
  `python3 /Users/mac_claw/.openclaw/workspace/skills/marketing-automation-suite/scripts/check_pr_readiness.py --repo-root /Users/mac_claw/.openclaw/workspace --allow-prefix skills/marketing-automation-suite --allow-prefix skills/prospect-data-engine --allow-prefix skills/marketing-strategy-engine --allow-prefix skills/outreach-feedback-engine --allow-prefix projects/neosgo-marketing-suite`
