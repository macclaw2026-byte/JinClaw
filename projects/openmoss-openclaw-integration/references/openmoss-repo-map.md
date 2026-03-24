# OpenMOSS Repo Map

本文件记录哪些 OpenMOSS 仓库对当前 OpenClaw 工作区有直接价值，以及建议吸收方式。

## 1. OpenMOSS/imclaw-skill

最相关能力：

- IMClaw Hub 实时通信
- queue + processed archive
- per-group session
- reply / config / bridge 分层

最值得借鉴的文件：

- `bridge_simple.py`
- `process_messages.py`
- `reply.py`
- `config_group.py`
- `references/session_rules.md`

本地吸收方式：

- 做成 in-house bridge 工具，而不是直接原样依赖
- 将 queue / archive / session 模型融合到本地 `skills/imclaw-bridge-ops`
- 用当前工作区现有的 hook / recovery / learning 体系包住它

## 2. OpenMOSS/OurClaw

最相关能力：

- single-bot + multi-backend + per-user isolation
- `commonworkspace`
- shared override config
- runtime-generated per-user `openclaw.json`

最值得借鉴的目录：

- `commonworkspace/`
- `openclaw-patch/`
- `TFClaw/`

本地吸收方式：

- 不直接迁移 TFClaw
- 先借鉴 common template 和 per-user config generation
- 后续如果要团队化，再引入 relay / user mapping 机制

## 3. OpenMOSS/MOSS-TTS

最相关能力：

- long-form TTS
- realtime streaming TTS
- sound effect / expressive voice
- API / FastAPI / CLI 入口都比较清晰

最值得借鉴的目录：

- `clis/`
- `moss_tts_realtime/`
- `moss_tts_local/`
- `moss_tts_delay/`

本地吸收方式：

- 优先接成独立 voice backend
- 从 OpenClaw 回复链路调用
- 先做文件输出和摘要播报，再做实时 streaming

## 4. OpenMOSS/MOSS-TTSD

最相关能力：

- 多角色对话式 TTS
- 批处理推理入口
- 适合播客化、日报主持人化输出

最值得借鉴的文件：

- `inference.py`
- `generation_utils.py`
- `gradio_demo.py`

本地吸收方式：

- 做成 `moss-voice-orchestrator` 的高级模式
- 不作为第一阶段必需能力

## 5. OpenMOSS/AnyGPT

最相关能力：

- any-to-any 多模态
- speech/image/music/text 统一入口

最值得借鉴的目录：

- `config/`
- `scripts/`
- `seed2/`

本地吸收方式：

- 不直接放入主 runtime
- 单独做 worker service
- 通过工具契约暴露给 OpenClaw

## 6. OpenMOSS/MOSS

定位：

- 重要的工具增强模型仓库

本地建议：

- 先学习其“工具增强和插件”思路
- 暂不作为当前工作区的第一阶段主模型替换目标
