# ACP Dispatch Request Builder

This builder converts JinClaw control-center coding metadata into a runtime-ready ACP dispatch request object.

## Guarantees
- JinClaw remains the authority for task routing and methodology selection.
- The resulting request is suitable for a future real spawn layer to consume directly.
- The prompt already includes the injected gstack-lite discipline when coding methodology is enabled.

## Required request fields
- `runtime`
- `mode`
- `thread`
- `session_kind`
- `prompt`
- `prompt_components`
- `env`
- `metadata`

## Current status
- Builder implemented and tested
- Real runtime spawn consumption not yet claimed unless a concrete caller wires it in
