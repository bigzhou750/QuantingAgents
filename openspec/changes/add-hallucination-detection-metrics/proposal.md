## Why

现有评测平台已经能够抽取 Claim、匹配 Evidence，并输出证据覆盖率和 unsupported ratio，但这些结果还不能回答“幻觉识别器是否有效”。需要补充可复现的人工真值、预测标签和分类指标，才能量化幻觉检测能力，并区分检测能力与证据质量评分。

## What Changes

- 为评测样本增加 Claim 级幻觉真值和标注来源，支持 `supported`、`unsupported`、`contradicted` 等状态映射。
- 基于现有 Claim-Evidence 判定生成幻觉预测标签，保留预测原因、阈值和评分器版本。
- 增加 TP、FP、FN、TN 统计，以及 Recall、Precision、F1 和无证据结论放行率计算。
- 支持按实体、数值、来源、时间、逻辑矛盾等幻觉类型聚合指标，并展示样本量和分母口径。
- 保持现有 evidence quality、Ragas 和普通评测结果兼容；缺少人工真值时不生成幻觉检测指标。

## Capabilities

### New Capabilities

- `hallucination-detection-metrics`: 提供 Claim 级幻觉标注、预测、混淆矩阵和可复现指标聚合能力。

### Modified Capabilities

- 无

## Impact

- Backend：扩展 `app/models/eval.py`、`app/services/eval/scorers/evidence_scorer.py`、`app/services/eval/metrics_service.py` 及评测 API 返回结构。
- Data：为 eval case/trial/score 增加 Claim 标注、指标版本和评测口径字段，兼容历史数据。
- Tests：补充 Claim 标签映射、混淆矩阵、边界样本和缺少真值时的跳过行为测试。
- API/UI：优先提供结构化结果和聚合接口；不改变现有普通问答流程，已有评测页面只增加可选指标展示。
