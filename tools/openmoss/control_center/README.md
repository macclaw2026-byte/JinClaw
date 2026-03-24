# Control Center

`control_center` is the single high-level orchestration brain for this workspace.

It does not replace the OpenClaw runtime. It sits above the OpenClaw runtime and
above the existing autonomy modules, and turns them into clearly separated
functional regions:

- `intent_analyzer`: understand the user's instruction
- `capability_registry`: inventory local tools, scripts, and skills
- `workflow_planner`: generate multiple candidate execution plans
- `proposal_judge`: score and choose the best plan with explicit rationale
- `plan_history`: accumulate plan outcomes so future routing gets smarter
  - this now blends exact-scene, task-type, risk-level, and global experience
- `resource_scout`: prepare compliant external discovery queries and source policy
- `domain_profile_store`: keep domain-specific fetch preferences and challenge posture
- `challenge_classifier`: recognize rate limits, auth walls, CAPTCHA-like gates, and rendering barriers
- `adaptive_fetch_router`: choose the compliant acquisition ladder from API/static fetch to browser, authorized session, or human checkpoint
- `authorized_session_manager`: define isolated reviewed session requirements for approved authenticated access
- `human_checkpoint`: pause automation safely when human verification is required
- `security_policy`: classify risk and define hard boundaries
- `approval_gate`: audit and approve or block external acquisition/execution
- `solution_arbitrator`: decide what to do when the mission stalls or needs external help
- `necessity_prover`: justify when a higher-risk or external-extension path is truly necessary before switching
- `problem_solver`: classify blockers and propose next actions
- `topology_mapper`: map dependencies, verification nodes, and risk nodes
- `fractal_decomposer`: recursively turn plan steps into verifiable sub-loops
  - stage execution can focus on a specific fractal loop instead of carrying the whole plan
- `htn_planner`: organize the mission into a hierarchical task network with stage and subtask focus
- `bdi_state`: expose beliefs, desires, and intentions for the current mission cycle
- `stpa_auditor`: audit unsafe control actions and block unsafe stage transitions before execution
- `forensic_simulator`: reconstruct lightweight decision traces for debugging and explanation
- `research_loop`: maintain a structured, approval-aware external research package
- `advisory_engine`: produce insights and recommendations after or during task execution
- `summary_compressor`: reduce mission/state into a compact summary
- `context_builder`: create minimal stage execution packets to reduce token usage
- `cache_store`: persist reusable lightweight artifacts
- `mission_loop`: run the whole control-center cycle on each task
- `mission_loop` also emits a structured `next_decision` so the runtime can move with less repeated reasoning
- `orchestrator`: build the execution blueprint handed to autonomy/OpenClaw

The OpenClaw runtime remains the execution substrate:

- ingress: Telegram / gateway / session transport
- execution: tool and session invocation
- egress: replies, reports, voice

The autonomy modules become internal control-center regions:

- planning
- preflight
- recovery
- verification
- learning

The design goal is one brain, many coordinated regions.
