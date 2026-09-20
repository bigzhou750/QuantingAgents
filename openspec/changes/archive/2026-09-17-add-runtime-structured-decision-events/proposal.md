## Why

当前 Vibe runtime 只产生 `thinking`、`tool_call`、`tool_result`、`text_delta` 和 `attempt.*` 等运行事件，并没有真正发出结构化决策事件。现有系统为了展示决策链，把工具调用、工具结果和任务完成事件强行归一化成 `DecisionRecord`，导致页面显示大量 `unverified`、`candidates_unavailable` 和直接跳到最终结论的记录，无法回答“为什么选 A 不选 B、依据是什么、读到哪一步得出结论”。

## What Changes

- 在 Vibe runtime 增加正式的 `decision.record` 事件契约，包含场景、候选方案、选中项、选择依据、结论、证据引用、父决策 ID、状态、置信度、风险等级、模型/策略版本和产生时间。
- AgentLoop 在关键节点发出真实决策事件：标的识别与锁定、工具授权/拦截、每一轮分析结论和最终研究判断。
- 工具调用与工具结果通过 `call_id` 关联为证据/执行事件，不再各自生成独立“工具调用决策”和“工具结果决策”。
- `attempt.completed` 不再生成决策记录，只保留为任务终态和最终输出；系统不得把生命周期事件冒充为分析结论。
- 当前基于事件类型的决策降级映射只用于兼容旧数据或缺失场景，必须在记录中显式标记 `unverified`/`candidates_unavailable`，并不得被审计页面当作完整决策链。
- 决策审计页面和评测页面展示真实决策节点、证据引用和缺失原因，并将“未获取到数据”作为证据获取结果记录，而不是直接变成“未作决策”。

## Capabilities

### New Capabilities

- `vibe-runtime-decision-events`: 提供 Vibe runtime 的结构化决策事件产出、工具证据关联、生命周期与决策分离、决策记录落库和审计展示契约。

### Modified Capabilities

<!-- 无：本 change 不修改已归档主规格中的现有能力。 -->

## Impact

- **Backend**：涉及 `app/services/vibe_agent/service.py`、`app/services/explainability/record_service.py`、`app/services/explainability/audit_service.py`、`app/services/eval/trace_adapter.py` 和决策记录/审计接口，保持现有 API 与旧数据兼容。
- **Runtime**：涉及 `vibe_agent_runtime/vendor/src/agent/loop.py`、`vibe_agent_runtime/vendor/src/agent/grounding.py`、`vibe_agent_runtime/vendor/src/session/service.py` 和事件总线，新增事件类型不改变现有工具权限与 provider 边界。
- **Frontend**：涉及 `frontend/src/views/Evaluation/DecisionAudit.vue`、`frontend/src/views/Evaluation/RunDetail.vue` 和事件名称映射，未获取数据与缺失决策依据使用可读中文提示。
- **Data**：新增或扩展 `decision.record` trace 事件、`agent_decision_records` 字段和证据引用；旧记录继续显示为 `unverified`/`legacy_unverified`，不伪造已有决策。
- **Testing**：增加 runtime 事件到决策记录、工具证据关联、生命周期事件不生成决策、审计链完整链路和前端展示的回归测试。
