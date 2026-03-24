# OpenMOSS Voice Runtime

这个目录预留给本地的 MOSS 语音运行时。

建议后续放入：

- `moss_tts_runner.py`
- `moss_tts_realtime_runner.py`
- `moss_ttsd_runner.py`
- `voices/`
- `outputs/`
- `health/`

## 目标

将 `OpenMOSS/MOSS-TTS` 与 `OpenMOSS/MOSS-TTSD` 接成当前工作区的语音能力层。

## 推荐顺序

1. 离线文件生成
2. 报告摘要播报
3. 消息附件投递
4. 多角色 dialog TTS
5. 实时流式 TTS
