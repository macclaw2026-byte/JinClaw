# Jin-gstack Skill Automation Plan

## Objective
把 Jin-gstack 中需要手工维护的 `tmpl` 前置步骤自动化，新增一个“问答模版 → 生成 tmpl → 继续走生成链”的本地优先方案；同时把 `think → plan → build → review → test → ship → reflect` 固化为一等流程，不做阉割，只允许轻微本地化适配。

## What we learned locally
- `tmp/Jin-gstack-compare/scripts/gen-skill-docs.ts` 是核心生成器：读取 `SKILL.md.tmpl`，解析 `{{PLACEHOLDER}}`，经 resolver 生成最终 `SKILL.md` 与部分 host 适配产物。
- `tmp/Jin-gstack-compare/scripts/discover-skills.ts` 说明当前发现模型是“根目录 + 一级子目录 + `SKILL.md.tmpl`”。
- `tmp/Jin-gstack-compare/autoplan/SKILL.md.tmpl` 证明 GStack 已把完整审查流程固化进模板源码，尤其保留了 think/plan/review/test/ship/reflect 的阶段语义。
- `compat/gstack/prompts/jinclaw-gstack-plan.md` 已经有 JinClaw 本地规划提示，可作为 lifecycle 对齐入口。
- 现有 compat 层原则明确：通过 compat adapter 吸收机制，保持 JinClaw 主导且所有产物可复现、可移除。

## Candidate execution paths

### Plan A — Minimal wrapper around existing compare corpus
- 直接在 workspace 新增一个 questionnaire 脚本，生成 `tmp/Jin-gstack-compare/<skill>/SKILL.md.tmpl`
- 然后直接复用 compare corpus 的 `gen-skill-docs.ts`
- 优点：最快
- 缺点：把生产流建立在 `tmp/` 实验语料上，不稳，边界脏，容易形成幽灵文件

### Plan B — Build a JinClaw-native skill scaffold system that imports the useful generation model
- 在 workspace 新增独立的 `tools/jingstack-skill-system/` 或 `projects/jingstack-skill-system/`
- 抽取 questionnaire schema、tmpl renderer、generation command、validation command
- 让 compat/gstack 提示与本地 skill 创建流程都指向这个系统
- 保留 lifecycle 流程为显式阶段，并产出测试证据
- 优点：边界清晰，可测试，可演进，可避免 `tmp/` 污染
- 缺点：实施量更大

### Plan C — Patch OpenClaw core skill loading/config directly first
- 先改 OpenClaw 技能触发或运行时核心，再倒逼模板系统适配
- 优点：能触及更深层
- 缺点：当前证据不足，风险过高，测试面太大，不符合本地安全优先

## Selected plan
**Plan B**

理由：
1. 符合“local-first safe execution”
2. 避免把正式链路绑死在 `tmp/Jin-gstack-compare`
3. 最容易满足你要求的“无幽灵文件、沟通调度顺畅、测试可举证”
4. 能保留并显式落实完整 lifecycle，而不是只复制几个 prompt

## Proposed architecture

### 1. Questionnaire layer
新增一套结构化问答模版，至少覆盖：
- skill slug / name
- user intent / trigger phrases
- core jobs to be done
- inputs / outputs
- required resources: scripts / references / assets
- safety boundaries
- lifecycle requirements
- review/test/ship expectations
- host/runtime notes

产物：
- `answers.json`
- `plan.md` 或 `spec.md`

### 2. tmpl synthesis layer
基于问答答案生成标准化 `SKILL.md.tmpl`：
- frontmatter 自动生成
- body sections 按约定拼装
- 如果启用 lifecycle，则自动写入完整阶段骨架：
  - think
  - plan
  - build
  - review
  - test
  - ship
  - reflect

### 3. generation layer
复用或移植 GStack 风格生成器的核心能力：
- 读取 tmpl
- 解析 placeholders
- 使用 resolver 生成最终 `SKILL.md`
- 支持 dry-run / freshness check / validation

### 4. orchestration layer
新增统一命令，例如：
- `create-questionnaire`
- `generate-tmpl`
- `generate-skill`
- `validate-skill`
- `test-skill-system`

### 5. compatibility wiring
更新：
- `compat/gstack/prompts/jinclaw-gstack-plan.md`
- 必要的 local docs / scripts
让系统在“需要新 skill”时优先走问答驱动模板流。

## Files/modules likely impacted
- new: `tools/` or `projects/` 下的 skill-system 目录
- update: `compat/gstack/prompts/jinclaw-gstack-plan.md`
- maybe update: `skills/skill-creator/SKILL.md` 或 workspace 内相关本地说明文件
- new: tests, fixtures, evidence outputs, change report

## Validation matrix
1. questionnaire → answers persisted
2. answers → tmpl generated deterministically
3. tmpl → SKILL.md generated deterministically
4. lifecycle sections preserved in generated outputs
5. dry-run/freshness validation works
6. no stray files outside declared output dirs
7. integration docs/prompt point to new flow
8. representative fixture passes end-to-end

## Risks
- GStack compare corpus 是参考实现，不一定能直接原样搬进生产路径
- resolver 抽取若不干净，可能引入多余 host/adapter 逻辑
- 如果直接修改太多现有 skills，回归面会变大

## Recommendation
先把 `tmp/Jin-gstack-compare` 中与模板生成直接相关的最小闭环抽出来，建立一个 JinClaw-native、边界干净的 skill-system；随后把 lifecycle 骨架内置进去，再做端到端测试与无幽灵文件检查。
