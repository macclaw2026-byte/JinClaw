# OpenMOSS Multi-Tenant Runtime

这个目录用于把 `OurClaw` 的 per-user workspace isolation 思路接到当前 OpenClaw 工程里。

当前目标：

- 用共享模板生成每个用户独立的 runtime 目录
- 为每个用户生成独立 `openclaw.json`
- 后续把 bridge / voice / memory / logs 逐步绑定到独立 runtime

当前实现：

- `provision_user_workspace.py`
- `templates/commonworkspace/`

设计原则：

- 不改写当前 `~/.openclaw`
- 所有生成物都放到 `tools/openmoss/runtime/users/`
- 默认复用共享模板，再叠加用户覆盖配置
