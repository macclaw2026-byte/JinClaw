# Browser Backend Risk Assessment

Primary risks:
- hidden coupling to coding-only assumptions
- persistent state leakage
- duplicate browser authority paths
- fallback ambiguity

Mitigation:
- adapter boundary
- feature flag
- explicit backend selection
- rollback to JinClaw-native backend
