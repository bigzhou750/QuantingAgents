## Why

项目已经能够保存 Agent 事件、工具调用、证据和评测 trace，但这些内容仍主要是事件日志或评测期结果，无法稳定回答“为什么做出这个决策、依据是什么、谁能追溯、解释是否与真实路径一致”。需要把现有 Vibe runtime、TradingAgents graph、评测平台和操作审计统一到生产级决策链上，补齐高风险场景的解释校验、观测和人工兜底能力。

## What Changes

- 新增统一的 `DecisionRecord` 和 `decision` trace 事件，记录决策场景、候选选项、选择依据、最终结论、关联证据、父子节点和策略/模型版本。
- 在 Vibe Agent runtime、TradingAgents graph 及工具调用链中采集节点级决策记录；工具决策同时保存候选工具、选中工具和未选原因，避免只记录最终调用。
- 新增分层解释能力，为开发者、业务人员和终端用户生成不同粒度的解释，不直接暴露原始模型思考内容。
- 新增解释一致性校验，核对解释与决策记录、证据和最终输出是否一致，并将不一致标记为低可信或需复核。
- 新增按 `business_id`/`task_id`/`session_id` 查询的统一审计接口，聚合决策链、trace、证据、最终结果、权限审计和复核记录。
- 将线上 Agent trace 与评测 trace 统一到同一事件契约，支持完整率、解释一致率、证据覆盖率、审计查询延迟和高风险暂停次数等生产指标。
- 新增解释链路故障时的降级策略：保留原始 trace，阻断高风险自主决策并转人工复核；低风险任务可带边界说明继续完成。
- 在现有研究工作台、评测后台和审计页面增加决策路径、关键转折点、候选比较、证据下钻和复核状态展示。

## Capabilities

### New Capabilities

- `agent-decision-explainability-audit`: 提供节点级结构化决策链、分层业务解释、一致性校验、统一审计查询、生产观测和故障降级能力。

### Modified Capabilities

- `agent-evaluation-platform`: 扩展标准 trace 和 trial 结果契约，使评测平台能够消费并展示决策节点、解释校验结果和线上审计关联，而不改变现有数据集、评分器和回归流程。

## Impact

- **Backend**：新增决策记录模型、trace 事件适配、解释/校验服务、审计聚合服务、生产指标和降级策略；涉及 `app/models/`、`app/services/vibe_agent/`、`app/services/eval/`、`app/routers/`、`app/core/`。
- **Core graph/runtime**：在 `tradingagents/graph/` 和 `vibe_agent_runtime/` 增加决策节点采集及上下文传递，不改变现有工具权限边界和模型 provider 接口。
- **Frontend**：研究工作台、评测 trial 详情和运维审计页面增加决策链与解释状态展示；普通用户仍只看到经过分层和脱敏的解释。
- **Data**：新增决策记录、解释版本、校验结果、审计关联和指标字段；历史数据保持可读，缺少新字段时显示为 `legacy_unverified` 或不可用，不伪造解释结果。
- **Permissions/Security**：统一审计链仅向有权限的研发、管理员或业务主体开放；原始 prompt、模型输出和证据继续遵守脱敏、用户隔离和受控存储规则。
- **Compatibility**：现有单股分析、批量分析、自然语言研究、评测运行和第三方 scorer 保持兼容；新增能力故障不得影响低风险普通任务的既有接口契约。
