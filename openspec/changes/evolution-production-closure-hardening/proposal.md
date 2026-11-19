## Why

自进化现在已经能从失败生成提案、验证并发布，但离生产完整闭环还有几处关键边界没有收紧：基线会漂移、冷却窗口没有真正参与去重、发布仍依赖补偿式一致性、线上反馈没有自动回流成 Bad Case 或停止动作，overlay 隔离也还停留在注入级别。要让系统可长期运行，这些控制面边界必须明确化。

## What Changes

- 将提案创建时的 baseline 固定为不可漂移的正式版本，并在后续验证和发布中持续校验
- 让冷却窗口真正参与触发去重与提案生成，而不是只作为配置存在
- 将 promote / rollback 的执行顺序和失败补偿收敛为明确的发布原子边界
- 将 post-release 观测结果自动回流为 Bad Case、stop 或 rollback 候选，而不是只停留在接口返回
- 将 overlay 验证从 prompt 注入升级为更强的隔离约束，并明确其在不同 runtime 组件中的边界

## Capabilities

### New Capabilities
- `evolution-production-closure`: 自进化控制面需要在基线锁定、冷却去重、反馈回流和隔离验证上形成生产闭环

### Modified Capabilities
- 无

## Impact

- app/services/evolution/proposal_service.py
- app/services/evolution/verification_service.py
- app/services/evolution/trigger_service.py
- app/services/evolution/governance_service.py
- app/services/evolution/promote_service.py
- app/routers/evolution.py
- app/services/evolution/clustering.py
- vibe_agent_runtime/runtime.py
- 与自进化控制面相关的数据库模型、事件日志和测试
