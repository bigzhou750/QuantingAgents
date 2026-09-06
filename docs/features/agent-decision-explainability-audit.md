# Agent 决策可解释与审计

本文说明 QuantingAgents 的 Agent 决策链、分层解释、一致性校验、统一审计、生产指标和降级配置。

## 决策链字段

每个关键决策节点会生成结构化 `DecisionRecord`，字段包括：

- `decision_id`、`sequence`、`parent_decision_id`
- `business_id`、`task_id`、`session_id`、`user_id`
- `decision_type`：`agent`、`tool`、`graph`
- `scenario`：决策场景
- `candidates`：候选选项及未选原因
- `selected_option`：最终选中项
- `selection_reason`：选择依据，缺失时标记 `candidates_unavailable` 或 `reason_unavailable`
- `conclusion`、`evidence_ids`
- `status`：`confirmed`、`unverified`、`requires_review`、`degraded`、`blocked`
- `confidence`、`risk_level`、`model_version`、`strategy_version`

Vibe runtime 和 TradingAgents graph 都向统一 trace 事件 `decision` 输出决策记录；线上事件与评测 trial 使用同一 `TraceAdapter` 契约。

## 分层解释

解释服务生成三层解释：

- 开发者：完整决策节点、候选比较、依据、证据 ID、模型和策略版本。
- 业务人员：精简逻辑说明和证据数量。
- 终端用户：自然语言理由，不暴露原始模型思考内容。

解释版本保存在 `agent_explanations`，用于后续审计和回归。

## 一致性校验

`ExplanationValidator` 会比较解释、决策记录、证据和最终输出，返回：

- `consistent`：解释与决策链一致。
- `inconsistent`：解释与决策记录冲突，高风险样本自动进入复核队列。
- `unverifiable`：缺少候选、依据、结论、证据或最终输出，不伪造解释结果。

校验结果保存在 `agent_explanation_validations`。

## 统一审计

管理员或业务主体可以按 `business_id`、`task_id`、`session_id` 或 `trial_id` 查询统一审计链：

```text
GET /api/decision-audit/chains/{identifier}
GET /api/decision-audit/metrics
GET /api/decision-audit/alerts
POST /api/decision-audit/reviews/{review_id}
```

响应会聚合决策链、trace、证据、最终输出、操作日志、解释、校验和人工复核记录。旧数据没有决策链时返回 `legacy_unverified`，保留已有 trace 和日志。

评测后台也提供：

```text
GET /api/eval/trials/{trial_id}/explainability
```

## 生产指标与告警

指标包括：

- 决策链完整率
- 解释一致性
- 证据覆盖率
- 审计查询延迟
- 高风险暂停次数

指标写入 `explainability_metrics`，支持按任务类型、模型版本和风险等级聚合。`EXPLAINABILITY_ALERT_THRESHOLD` 低于阈值时通过现有 governance 配置和通知渠道告警。

## 降级配置

后端配置项：

- `EXPLAINABILITY_ENABLED`：是否启用决策链、解释和校验。
- `DECISION_AUDIT_ENABLED`：是否启用统一审计接口。
- `EXPLAINABILITY_MODE`：`strict` 或 `relaxed`。
- `EXPLAINABILITY_HIGH_RISK_THRESHOLD`：高风险阈值。
- `EXPLAINABILITY_ALERT_THRESHOLD`：告警阈值。

解释链路故障时：

- 低风险任务保留结果和原始 trace，并标记解释缺失。
- 高风险任务暂停后续自主决策，保存全量原始事件，并创建 `agent_decision_reviews` 人工复核记录。

## 数据存储

新增集合：

- `agent_decision_records`
- `agent_explanations`
- `agent_explanation_validations`
- `agent_decision_reviews`
- `explainability_metrics`

旧数据不迁移也不会被覆盖；缺少新字段时按 `legacy_unverified` 或不可用状态处理。
