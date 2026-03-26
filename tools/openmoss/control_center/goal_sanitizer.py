#!/usr/bin/env python3

from __future__ import annotations

import re


def sanitize_goal_text(text: str) -> str:
    cleaned = str(text or "")
    patterns = [
        r"Conversation info \(untrusted metadata\):\s*```json.*?```\s*",
        r"Sender \(untrusted metadata\):\s*```json.*?```\s*",
        r"Replied message \(untrusted, for context\):\s*```.*?```\s*",
    ]
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"^\[Queued messages while agent was busy\]\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^---\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^Queued\s+#\d+\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^System:\s.*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned or str(text or "").strip()
