#!/usr/bin/env python3
"""Example helper for updating github-open-source-scout state.

This is intentionally lightweight and meant as a future reusable pattern,
not a full production tracker.
"""

import json
from pathlib import Path
from datetime import datetime

state_path = Path('.state/github-open-source-scout.json')
state_path.parent.mkdir(parents=True, exist_ok=True)
if state_path.exists():
    state = json.loads(state_path.read_text())
else:
    state = {"lastRun": None, "cadence": "2d", "projects": []}
state["lastRun"] = datetime.now().astimezone().isoformat()
state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
print(state_path)
