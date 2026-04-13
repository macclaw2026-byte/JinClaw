<!--
RULES-FIRST NOTICE:
Before modifying this file, first read:
- `JINCLAW_CONSTITUTION.md`
- `AI_OPTIMIZATION_FRAMEWORK.md`
Follow the constitution and framework:
brain-first, one-doctor, fail-closed, evidence-over-narration,
validate locally, then use the required PR workflow.
-->
# Orchestrator Governance Upgrade

## 升级目标

本次升级不是推倒重写，而是在保留现有 `contract / stage / metadata / verifier` 主链的前提下，把 `orchestrator.py` 升级为：

- 多档治理模型
- 角色化计划审议链
- 统一 operating discipline
- 分层 knowledge basis
- 带 remediation 的 verifier guidance
- protocol pack
- readiness dashboard

整体方法论吸收自 `Jin-gstack` 的几个核心优点：

- 显式生命周期 discipline，而不是隐式经验
- 多角色 review，而不是只看单分数
- search-before-build 与 layered knowledge
- Boil the Lake 式完整交付倾向
- user sovereignty：AI 推荐，用户决策

## 新增核心结构

### 1. `governance`

解决的问题：

- 原来只有“复杂 / 不复杂”两档，不够细腻
- plan-only 任务会被误当成交付任务处理

新增结果：

- `tier`: `lite / standard / reviewed / mission / plan_only`
- `policy`: 阶段治理策略、review 强度、artifact/verifier/postmortem 要求

兼容方式：

- 旧字段 `complex_task_controller` 仍保留
- 但其行为 now 由新的 `governance` 映射生成，避免双轨漂移

### 2. `plan_reviews`

解决的问题：

- 过去主要依靠候选方案评分，缺少显式的多视角审议

新增结果：

- `product_review`
- `engineering_review`
- `design_review`
- `security_review`
- `devex_review`

每个 review 统一输出：

- `summary`
- `concerns`
- `recommendations`
- `must_fix_before_execute`
- `ask_user_before_changing_direction`

### 3. `operating_discipline`

解决的问题：

- `coding_methodology / goal_guardian / doctor hints / complex controller` 原来分散，难以统一消费

新增结果：

- `principles`
- `execution_rules`
- `escalation_rules`
- `completion_rules`
- `enabled_rule_keys`

关键纪律包括：

- `search_before_build`
- `user_sovereignty`
- `must_produce_evidence`
- `must_write_postmortem_before_close`
- `deep_research_before_ask_user`
- `ask_user_when_direction_changes`
- `fail_closed_on_uncertain_permissions`
- `self_review_before_done`

### 4. `knowledge_basis`

解决的问题：

- 过去的 search/scout 更偏“去哪找”，缺少“这些知识属于哪一层”的判断

新增结果：

- `layer1_candidates`: 稳定成熟共识
- `layer2_candidates`: 新而流行但需谨慎
- `layer3_observations`: 本任务独有 first-principles 推理
- `recommended_basis`
- `eureka_moments`
- `known_uncertainties`

### 5. `verification_guidance`

解决的问题：

- verifier 过去更像 pass/fail 检查器，失败后下游容易卡住

新增结果：

- `failure_modes`
- `recommended_next_actions`
- `can_retry`
- `should_replan`
- `requires_human_decision`

### 6. `protocol_pack`

解决的问题：

- 不同强度任务缺少显式协议包，spawn/runtime 不知道应该走 lite/full/plan-only 哪条链

新增结果：

- `orchestrator-lite`
- `orchestrator-standard`
- `orchestrator-full`
- `orchestrator-mission`
- `orchestrator-plan-only`

### 7. `readiness_dashboard`

解决的问题：

- 系统过去难以结构化解释“为什么还不能进入下一阶段”

新增结果：

- `plan_readiness`
- `execute_readiness`
- `verify_readiness`
- `release_readiness`
- `blocking_items`
- `missing_artifacts`
- `pending_decisions`

## 兼容策略

保留不变：

- `build_control_center_package()` 继续作为总装配入口
- 现有 `stage contract` 主流程保留
- 现有 `coding_methodology / goal_guardian / complex_task_controller` 保留

新增兼容补齐：

- `control_center_schemas.py` 抽出 stage/verifier/governance/protocol/readiness schema
- `runtime_service.py` 新增统一升级 bundle，用于给旧 contract 自动回填：
  - `governance`
  - `plan_reviews`
  - `operating_discipline`
  - `protocol_pack`
  - `knowledge_basis`
  - `readiness_dashboard`

## 消费链路

新增结构不是“只堆 metadata”，而是已经接入下游：

- `proposal_judge.py`
  - 消费 `knowledge_basis`
- `solution_arbitrator.py`
  - 消费 `knowledge_basis / plan_reviews / governance`
  - 落地 `direction_change_recommendation / requires_user_confirmation`
- `context_builder.py`
  - 暴露 `governance / plan_reviews / operating_discipline / protocol_pack / knowledge_basis / readiness_dashboard / verification_guidance`
- `coding_session_adapter.py`
  - 把治理层与协议层注入 ACP prompt
- `acp_dispatch_builder.py`
  - 输出 `JINCLAW_GOVERNANCE_TIER / JINCLAW_PROTOCOL_PACK`
- `action_executor.py`
  - 在 runtime dispatch prompt 中透传新结构
- `mission_loop.py`
  - selected plan 变化时刷新 `plan_reviews / knowledge_basis / arbitration`

## 示例输出

### 1. 小任务 `lite`

输入：

```text
Fix a README typo in the local docs
```

关键字段：

```json
{
  "governance": {"tier": "lite"},
  "protocol_pack": {"pack_id": "orchestrator-lite"},
  "plan_reviews": {
    "active_reviewers": ["engineering_review", "security_review"]
  },
  "stages": ["understand", "plan", "execute", "verify", "learn"]
}
```

### 2. 评审型任务 `reviewed`

输入：

```text
Review and improve the runtime verifier architecture with implementation notes and test strategy
```

关键字段：

```json
{
  "governance": {"tier": "reviewed"},
  "protocol_pack": {"pack_id": "orchestrator-full"},
  "plan_reviews": {
    "active_reviewers": [
      "product_review",
      "engineering_review",
      "design_review",
      "security_review",
      "devex_review"
    ]
  },
  "knowledge_basis": {"recommended_basis": "layer1+layer3"}
}
```

### 3. 大型任务 `mission`

输入：

```text
Build a complete marketplace operations dashboard with backend, frontend, tests, and deployment handoff
```

关键字段：

```json
{
  "governance": {"tier": "mission"},
  "complex_task_controller": {"enabled": true},
  "protocol_pack": {"pack_id": "orchestrator-mission"},
  "readiness_dashboard": {
    "blocking_items": [
      {"type": "must_fix_before_execute", "stage": "plan"}
    ]
  }
}
```

### 4. 纯规划任务 `plan_only`

输入：

```text
先给我出一个完整实施方案，不要实施，不要写代码，只做规划和评审包
```

关键字段：

```json
{
  "governance": {"tier": "plan_only"},
  "protocol_pack": {"pack_id": "orchestrator-plan-only"},
  "stages": ["understand", "plan", "verify", "learn"],
  "readiness_dashboard": {
    "execute_readiness": {"applicable": false}
  }
}
```

## 验证方式

### 治理等级推导

看点：

- 小修类任务是否进入 `lite`
- 多角色评审但非完整交付任务是否进入 `reviewed`
- 完整交付是否进入 `mission`
- 只规划任务是否进入 `plan_only`

### 角色 review 是否生成

看点：

- `metadata.control_center.plan_reviews.active_reviewers`
- `metadata.control_center.plan_reviews.reviews`
- `must_fix_before_execute`

### verifier guidance 是否存在

看点：

- `stage["verification_guidance"]`
- `failure_modes`
- `recommended_next_actions`

### readiness dashboard 是否合理

看点：

- `blocking_items`
- `pending_decisions`
- `execute_readiness.applicable`
- `release_readiness.requires_postmortem`

## 测试入口

本次新增测试：

- `tests/test_orchestrator_governance_upgrade.py`

核心覆盖：

- `lite / reviewed / mission / plan_only` 分档
- role review 生成
- verifier guidance 生成
- readiness dashboard 生成
- context/dispatch 对新治理对象的消费
- direction change arbitration 的 user confirmation 规则
