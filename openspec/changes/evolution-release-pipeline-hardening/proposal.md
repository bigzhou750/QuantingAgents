## Why

当前自进化的发布动作对 Skill 只做了最小写盘和缓存失效，适合本地开发，但还不够生产化：版本边界不够硬、回滚与审计不够统一、不同 artifact 类型的发布方式也没有一个共同约定。随着系统开始覆盖多种 artifact，需要把“发布”升级成一条可审计、可回滚、可分环境的正式链路。

## What Changes

- 将发布定义为“版本推进”，而不是直接覆盖当前生效文件
- 为 Skill、Prompt、Policy、Rubric、Case 引入统一的发布入口和 materialization 约定
- 发布时保留旧版本、当前版本指针和完整的审批 / 验证回执
- 将 Skill 的文件写入视为运行时 materialization，而不是唯一事实来源
- 增加发布前校验、发布后校验、回滚和环境隔离要求
- 让发布状态、当前版本和历史版本在后台可查询、可审计

## Capabilities

### New Capabilities
- `evolution-release-pipeline`: 自进化 artifact 的发布、回滚和环境化生效需要版本化控制

### Modified Capabilities
- 无

## Impact

- app/services/evolution/*
- app/models/evolution.py
- app/routers/evolution.py
- vibe_agent_runtime/runtime.py
- vibe_agent_runtime/vendor/src/agent/skills.py
- frontend/src/views/Evolution/*
- 与自进化发布相关的测试与运维配置
