## Why

当前评测系统已经能生成 Claim、系统预测 `prediction_label` 和幻觉分类指标，但真实 Precision/Recall/F1 依赖人工 `truth_label`。这套真值目前没有数据集预置结构、批量导入入口或完整的前端标记流程，导致新 Run 跑完后指标始终是 `not_available`，无法支撑“300+ 离线评测集、recall≥95%、F1≥93%”这类可复现的评测结论。

## What Changes

- 为 `EvalCase` 增加可选的 `gold_claims` 真值结构，保存 Claim 原文、`truth_label`、`hallucination_type`、`evidence_refs`、`label_version` 和来源；同步写入 run snapshot，保证离线评测集可复现。
- 支持 `hallucination_seeds` 或等价模式，预置“出现即视为幻觉”的负样本断言，用于工具结果、实体、数值和证据冲突类评测。
- 增加批量 ground truth 导入能力，支持从 JSON/CSV 批量写入 `eval_scores.claims[].truth_label`，不再要求每条 Claim 都通过人工 UI 逐条提交。
- 将 Claim 标注入口接入人工复核页面：复核人员可以直接为 Claim 选择 `supported/unsupported/contradicted/excluded`，填写幻觉类型、证据引用和 `label_version`。
- 明确 `review_strategy` 语义并让 Claim 标注队列按策略工作：支持全量标注、低置信度/低分优先和抽样标注三种模式；指标结果必须展示标注覆盖率，避免把有偏子集指标当成全量指标。
- 指标聚合增加标注覆盖信息，包括已标注 Claim、未标注 Claim、参与指标 Claim、排除原因和标签版本；未达到最小标注覆盖率时 MUST NOT 输出可用 Precision/Recall/F1。
- 新增 Claim 级 LLM 判官，输出 `claim_id`、`verdict`、`prediction_label` 和判定原因，与现有规则型 Evidence Scorer 并存；幻觉分类指标按评分器版本分别聚合，不能把 LLM Judge 的连续质量分混入分类指标。

## Capabilities

### New Capabilities
- `claim-ground-truth-workflow`: 提供数据集级 Claim 真值、批量导入、人工标注队列、标注覆盖率和可复用离线评测集能力。
- `claim-level-llm-judge`: 提供 Claim 级 LLM 幻觉预测，作为规则型 Evidence Scorer 之外的独立预测来源。

### Modified Capabilities
- `agent-evaluation-platform`: `EvalCase` 和 run snapshot 增加可选结构化 gold claims；人工复核和 Claim 标注流程从展示恢复为可写工作流；`review_strategy` 成为实际生效的复核/标注策略。

## Impact

- Backend: 涉及 `app/models/eval.py`、`app/services/eval/dataset_service.py`、`app/services/eval/runner_service.py`、`app/services/eval/metrics_service.py`、`app/routers/eval.py`、`app/services/eval/scorers/evidence_scorer.py`，新增 Claim Judge scorer/适配器。
- Frontend: 涉及 `frontend/src/views/Evaluation/HumanReview.vue`、`RunDetail.vue`、`DatasetDetail.vue` 和 `evalClient.ts`，增加 Claim 打标表单、标注覆盖率展示和真值导入入口。
- Data/API: 新增可选字段和批量导入接口；`gold_claims` 与 `hallucination_seeds` 必须进入 run snapshot，已有 `expected_output`、`scoring_criteria` 和 `eval_scores.claims` 兼容。
- Metrics: 新增标注覆盖率、排除原因、评分器版本分流和 LLM 预测来源；未标注样本仍不参与分类指标。
- Compatibility: 所有新增字段可选，历史 case、历史 run 和未标注 Claim 不向后破坏；LLM Judge 不改变现有连续质量分接口。
- Testing: 覆盖 gold claims 导入、run snapshot 固化、批量真值写入、Claim 打标 UI、标注覆盖率边界、LLM Claim Judge 输出和多评分器指标聚合。
