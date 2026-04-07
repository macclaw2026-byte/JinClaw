# ACP Coding Session Adapter

This adapter defines how JinClaw-owned control-center metadata should be translated into a coding-session prompt payload.

## Rules
- JinClaw remains the routing authority.
- Coding methodology injection is allowed only when `coding_methodology.enabled == true`.
- Inject the full `jinclaw-gstack-lite` prompt before the task-specific execution request.
- Do not claim live ACP integration if the runtime spawn layer has not consumed the adapter yet.
- Treat this adapter as the contract between control-center planning and future runtime/session spawn code.

## Payload fields
- `session_kind`
- `methodology`
- `base_prompt`
- `final_prompt`
- `recommended_runtime`
- `recommended_mode`
- `requires_prompt_injection`
