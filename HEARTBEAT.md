# HEARTBEAT.md

## Active progress reminder task

When a heartbeat arrives, check whether the product-selection automation / Amazon premium wholesale automation work is still in progress.

If it is still in progress and Jacken has not received an update within the last 10 minutes, send a concise progress update instead of HEARTBEAT_OK.

Progress update should include:
- current focus
- what was completed since last update
- what is still blocked or unfinished
- next step

If the work is fully completed and Jacken has not yet been told, send the completion update instead of HEARTBEAT_OK.

If there is no active in-progress work needing reminder output, reply HEARTBEAT_OK.
