# JinClaw Zero-Dependency Tests

Run the current integration and consistency tests without external Python packages:

```bash
tools/bin/jinclaw-test
```

This suite currently validates:
- skill questionnaire -> scaffold generation
- end-to-end generated skill flow
- compat/gstack prompt and routing docs
- generated manifest consistency
- no leftover ghost temp/backup/orig files in the newly managed paths introduced by this integration
- coding-task methodology injection into control-center packages and stage context
- ACP/coding session adapter payload assembly from control-center metadata
- ACP dispatch request building for a future real spawn layer
- runtime main-path dispatch prompt integration for coding vs non-coding tasks
- canonical single-doctor architecture and integrated gstack coverage under the system doctor
- compatibility shim behavior for legacy gstack doctor entrypoints

All tests use Python standard library `unittest` only.
