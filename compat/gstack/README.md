# GStack Compatibility Layer for JinClaw

This directory contains JinClaw-owned compatibility work for selectively absorbing high-value mechanisms from Jin-gstack without surrendering JinClaw control, governance, or runtime authority.

Design rules:
- JinClaw remains the control center and source of truth.
- GStack-derived capabilities enter through compat adapters only.
- High-risk core runtime and governance paths remain JinClaw-native.
- All generated artifacts must be reproducible and removable.
