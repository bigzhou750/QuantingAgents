## Context

现有 Vibe runtime 通过 `AgentLoop._emit()` 把事件写入 `SessionService` 的 EventBus，再由 `EmbeddedAgentRuntime._on_event()` 转发给 `VibeAgentService.ingest_worker_event()`。这个管道已经支持任意事件名和结构化 payload，因此新增 `decision.record` 不需要重新搭建事件通道。

当前缺口在事件生产端：`AgentLoop` 只发出 `thinking`、`reasoning_delta`、`tool_call`、`tool_result`、`tool_progress`、`llm_usage`、`goal.updated` 和 `text_delta`；`SessionService` 只发出 `attempt.*` 生命周期事件。仓库中已经存在 `DecisionRecordDoc`、`decision_record_store`、TraceAdapter 的 `decision` 映射和审计页面，但没有任何 runtime 消费端真正产生 `decision.record`。

## Goals / Non-Goals

**Goals:**

- 建立 runtime 到 `agent_decision_records` 的真实决策事件通道。
- 先落地确定性决策：标的识别、工具授权/拦截、最终回答 grounding。
- 将工具调用和工具结果作为证据，通过 `call_id` 与决策节点关联。
- 停止把 `attempt.completed` 包装成“任务完成结论”决策。
- 保持旧事件、旧审计查询和旧数据兼容。

**Non-Goals:**

- 不强制模型在每一轮输出结构化 JSON 决策，避免改变 LLM 调用格式和成本模型。
- 不重写 AgentLoop 的 ReAct 主循环、工具批量调度和 provider 适配层。
- 不在本 change 中重建数据源或修复具体数据源 403/空数据问题；数据缺口只作为证据状态进入决策链。
- 不删除历史 `agent_decision_records` 或把旧占位记录改名为真实决策。

## Decisions

### 1. 使用现有 EventBus 新增 `decision.record` 事件

在 `AgentLoop` 和 `GroundingLedger` 中新增 `self._emit("decision.record", payload)`，payload 直接使用 `DecisionRecordDoc` 的字段契约。`VibeAgentService.ingest_worker_event()` 把该事件类型映射到现有 `VibeEventType` 白名单外的新 `decision` 类型，并调用现有 `_persist_decision_record()`。

**Rationale:** 复用现有 sink、TraceAdapter、Mongo 索引和审计聚合，不需要新增连接器。

**Alternative considered:** 继续由 `VibeAgentService` 把 `tool_call` 后处理成决策。这种方式无法恢复候选、理由和证据，已证明会产生 `candidates_unavailable` 假链，因此不作为主路径。

### 2. 先由确定性决策点发出真实记录

第一版从以下确定性边界发 `decision.record`：

- `GroundingLedger` 完成标的识别或冲突判断时：已有 `IdentityRecord` 的 `candidates`、最终 symbol、source、status 和 `source_tool_call_id`，可直接映射。
- `GroundingLedger.authorize_tool_call()` 产生 allow/block 时：候选为工具标识/授权失败原因，选择为 allow 或 block。
- `GroundingLedger.validate_final_answer()` 产生接受、拒绝、恢复或安全回退时：记录最终回答是否通过 grounding。
- `AgentLoop` 成功执行一个工具批次的入口：从当前工具注册表中取已注册工具作为候选，以本次调用为选择，以模型该轮 reasoning tail 为选择理由；reasoning 不可用时标记 `reason_unavailable`。

**Rationale:** 这些节点已经有结构化候选或规则结果。先保证“确定性决策”可信，再扩展 LLM 分析层面的决策。

**Alternative considered:** 在最终回答中提示模型输出 JSON 决策解释。成本高且容易与流式输出冲突，放在后置阶段，不阻塞确定性决策落地。

### 3. 工具调用和工具结果合并为证据节点

保留 `tool_call`/`tool_result` 原始运行事件，但决策链用 `call_id` 把它们作为证据关联。新增小型内存 `ToolEvidenceIndex`，按 `call_id` 记录工具名、参数摘要、结果状态、结果摘要和证据 ID；`decision.record` 只要引用 `call_id`，审计侧就能展开对应证据。

**Rationale:** 一次工具执行是一个事实来源，不是两个决策。这也避免页面出现“工具调用决策 + 工具结果决策”两行重复。

**Alternative considered:** 修改 `_persist_decision_record()` 自动合并 tool call/result。无法区分哪次工具结果被后续决策真正引用，不能自动合并。

### 4. 生命周期事件退出决策白名单

从 `VibeAgentService` 决策事件集合中移除 `attempt.completed` 和 `attempt.failed`，并移除 `_finalize_task_explainability()` 中“无记录时生成 attempt.completed 任务完成结论”的回退。最终输出继续由 `vibe_agent_messages` 和 `final_output` 承担。

**Rationale:** 任务终态不是推理节点；这条回退是当前“直接完成结论”现象的直接来源。

### 5. 数据缺口进入证据状态

工具返回空或错误时，`ToolEvidenceIndex` 记录 `status=unavailable` 和原始错误摘要。决策节点可以引用该证据 ID，并在 `selection_reason` 或 `conclusion` 中说明“依赖的数据未获取”。审计表格将“未获取到”显示为证据缺失，而不是把整条链路标成已完成。

**Rationale:** 截图中的大量“未获取到”来自运行时选择不调用、空结果和接口错误三类情况；统一记录能区分“没有调用”“调用失败”“调用成功但无数据”。

## Risks / Trade-offs

- [Risk] runtime 新增事件后事件量增加 → Mitigation: `decision.record` 保持紧凑字段，长文本只存摘要或引用；heartbeat 已有节流，不重复发送大内容。
- [Risk] 工具注册表候选过多导致每条工具决策过大 → Mitigation: 候选只保存过滤后的可执行工具名或 top-N，避免把完整工具描述写入决策记录。
- [Risk] 模型 reasoning tail 可能包含非决策内容 → Mitigation: 先使用 grounding 确定性子集；LLM 分析节点若引用 reasoning，必须标记来源为 `model_reasoning` 且缺失时 `unverified`。
- [Risk] 旧占位记录继续显示，用户误以为已修复 → Mitigation: 审计页根据事件的确定性来源标记记录类型；旧记录保持 `unverified`/`legacy_unverified`，不被计入完整链指标。
- [Risk] 并行工具调用导致父子关系复杂 → Mitigation: 使用 `attempt_id` + 当前迭代作为父决策 ID 分组，工具决策并行节点共享同一父节点。

## Migration Plan

1. 先增加 runtime `decision.record` 事件定义、`ToolEvidenceIndex` 和事件透传，默认由 feature flag 控制。
2. 接入 `GroundingLedger` 的确定性决策，通过 runtime fixture 验证标的识别、授权和最终回答 grounding。
3. 修改 `VibeAgentService` 决策白名单：只接受 `decision.record` 和真实决策事件；`attempt.completed` 保留为最终输出，不写决策记录。
4. 更新审计聚合和前端展示：真实决策节点显示候选/依据/证据，事件链和缺失数据使用独立标签。
5. 补充测试：runtime emit → sink → `decision_record_store` → audit API → 前端字段的端到端链路。

**Rollback:** 关闭 runtime 决策事件 feature flag；保留 `EXPLAINABILITY_ENABLED` 旧路径作为降级，但默认不再把工具和生命周期事件伪装成决策。历史记录不删除。

## Open Questions

- LLM 分析结论节点需要什么触发点才能稳定产生“候选/依据/结论”字段，而不退化成一轮轮 thinking 摘要？该问题可在确定性节点上线后，用真实任务采样决定，不需要在本 change 中预先固定。
