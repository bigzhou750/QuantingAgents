## 1. Runtime Event Contract

- [x] 1.1 在 `app/services/vibe_agent/models.py`、`app/services/eval/trace_adapter.py` 和服务事件映射中增加 `decision.record`，并验证新增单元测试确认事件名能映射到现有 `DecisionRecordDoc`/`TraceEventType.DECISION`
- [x] 1.2 在 runtime 侧实现 `ToolEvidenceIndex`：按 `call_id` 合并 `tool_call`/`tool_result`，记录工具名、参数摘要、结果状态、结果摘要和证据 ID，并用单测验证并行工具也能正确配对
- [x] 1.3 让 `VibeAgentService.ingest_worker_event()` 接收 `decision.record` 并调用 `_persist_decision_record()` 与 `_save_standardized_trace()`，用集成测试验证一条事件能写入 `agent_decision_records` 和 `eval_trace_events`

## 2. Deterministic Decision Emission

- [x] 2.1 在 `GroundingLedger` 标的识别完成时发出 `decision.record`，payload 包含候选标的、最终 symbol、来源、状态和 `source_tool_call_id`，用 graph/runtime fixture 验证记录字段
- [x] 2.2 在 `GroundingLedger.authorize_tool_call()` 的 allow/block 结果处发出 `decision.record`，候选为工具/授权结果，状态区分 confirmed 或 blocked，用 fixture 验证
- [x] 2.3 在 `GroundingLedger.validate_final_answer()` 的接受、拒绝、纠正和安全回退处发出 `decision.record`，并验证不把最终回答伪装成已确认结论
- [x] 2.4 在 `AgentLoop` 工具批次执行入口发出“工具选择决策” `decision.record`，候选来自工具注册表，选择为实际调用工具，reasoning 缺失时标记 `reason_unavailable`，用 runtime 单测验证

## 3. Stop Treating Events As Decisions

- [x] 3.1 从 `VibeAgentService` 决策事件集合中移除 `attempt.completed` 和 `attempt.failed`，并验证生命周期事件不再写入 `agent_decision_records`
- [x] 3.2 移除 `_finalize_task_explainability()` 中无决策记录时生成 `attempt.completed` 任务完成结论的回退，并验证无真实决策的任务返回 `events_without_chain` 而不是伪造完成结论
- [x] 3.3 调整 `tool_call`/`tool_result` 归一化逻辑，使工具事件只作为证据写入，不再自动生成“工具调用决策/工具结果决策”，用审计链测试验证

## 4. Evidence and Missing Data

- [x] 4.1 扩展 `ToolEvidenceIndex` 将空结果、接口错误和未调用数据记为 `unavailable`/`not_requested` 证据，并验证审计接口能返回证据状态
- [x] 4.2 允许 `decision.record` 通过 `call_id` 或 `evidence_ids` 引用证据，并在审计 API 中展开对应证据摘要，用聚合测试验证决策与证据关联
- [x] 4.3 更新决策记录生成逻辑，使“未获取到数据”出现在证据缺失状态而不是决策依据占位符，用截图对应任务样例验证输出

## 5. Audit and Frontend

- [x] 5.1 在 `DecisionAuditService.build_audit()` 中区分真实决策节点、运行事件、证据事件和缺失数据，并验证 `complete`/`partial`/`events_without_chain` 状态仍兼容
- [x] 5.2 更新 `DecisionAudit.vue` 和 `RunDetail.vue`：真实决策显示场景/候选/依据/结论/状态/风险，证据显示可用或缺失状态，用前端 type-check 和组件测试验证
- [x] 5.3 将 `candidates_unavailable`、`reason_unavailable` 显示为“未提供候选/未提供依据”等可读中文，并验证未知事件名仍保留原始名称

## 6. End-to-End Verification

- [x] 6.1 新增端到端测试：runtime 发出 `decision.record` → `ingest_worker_event()` → `decision_record_store` → audit API → 前端字段，全部通过
- [x] 6.2 新增旧数据回归测试：旧占位记录仍返回 `unverified`/`legacy_unverified`，不进入完整链指标，且新逻辑不影响历史审计查询
- [x] 6.3 增加 feature flag 回滚测试：关闭 runtime 决策事件后保留旧事件透传和旧数据可读，运行相关 pytest 全部通过
