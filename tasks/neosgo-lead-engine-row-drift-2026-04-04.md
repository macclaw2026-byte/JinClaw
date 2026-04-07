# Neosgo lead engine row-count drift note (2026-04-04)

## Current live counts
- raw_contacts: 67,382,866
- normalized_contacts: 67,382,866
- deduped_contacts: 40,800,031
- scored_prospects: 40,422,503
- outreach_ready_leads: 2,391,788
- outreach_queue pending: 2,990,884
- outreach_events: 53

## 2026-03-28 prior verification snapshot
- raw_contacts: 67,382,866
- normalized_contacts: 67,382,866
- deduped_contacts: 58,752,942
- scored_prospects: 56,330,054
- outreach_ready_leads: 3,282,296
- outreach_queue pending: 2,976,361
- outreach_events: 3

## Interpreted drift
- Raw and normalized layers are stable.
- Dedupe/scoring/outreach-ready layers are materially smaller now, implying later pruning, tighter filtering, partial rebuild, or updated scoring logic after 2026-03-28.
- Outreach events increased from 3 to 53, showing the operating layer continued after the earlier snapshot.
- Queue pending increased slightly despite fewer outreach-ready leads, which is consistent with queue persistence across runs.

## Execution implication
- Do not full-rebuild blindly.
- Treat current live DB as authoritative and use compatibility views + future targeted verification/rebuilds only where drift matters.
