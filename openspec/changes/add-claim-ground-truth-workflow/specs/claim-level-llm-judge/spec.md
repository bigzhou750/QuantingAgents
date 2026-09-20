## Purpose

提供 Claim 级 LLM 幻觉预测来源，使系统在规则型 Evidence Scorer 之外，能用 LLM 对每条 Claim 的实体、证据、工具结果和数值一致性给出独立判定。

## ADDED Requirements

### Requirement: LLM claim judge must return per-claim hallucination prediction

LLM Claim Judge MUST 接收最终输出、Claim 列表、证据片段、工具结果和可用的 gold claims，并逐条返回 `claim_id`、`verdict`、`prediction_label`、`prediction_reason` 和判定方法。`unsupported` 或 `contradicted` MUST 映射为预测幻觉，`supported` MUST 映射为非幻觉，无法判断的 Claim MUST 返回 `unscorable` 且 `prediction_label` 为 `null`。

#### Scenario: Judge predicts hallucination
- **WHEN** LLM Claim Judge 判断某条输出的数字与工具结果矛盾
- **THEN** 系统保存该 Claim 的 `contradicted` 判定、`prediction_label=true` 和结构化判定原因

#### Scenario: Judge cannot reach a decision
- **WHEN** LLM Claim Judge 缺少证据或认为样本不可判定
- **THEN** 系统保存 `unscorable` 且 `prediction_label=null`，该 Claim 不参与分类指标

#### Scenario: Judge dependency unavailable
- **WHEN** Judge 模型、凭据或调用通道不可用
- **THEN** 系统 MUST NOT 生成伪预测，评分结果标记为 `not_configured` 或 `error`

### Requirement: LLM judge metrics must stay independent from quality scores

幻觉分类指标 MUST 能够按预测来源和评分器版本分别聚合；LLM Claim Judge 的 `prediction_label` MUST NOT 与现有的 LLM 连续质量分、Ragas 或 DeepEval 分数合并计算 Precision/Recall/F1。同一批 Claim 存在多个预测来源时，系统 MUST 保留各来源结果并允许分别查看。

#### Scenario: Compare two predictors
- **WHEN** 同一 Claim 集合同时存在规则型 Evidence Scorer 和 LLM Claim Judge 预测
- **THEN** 系统按 scorer name 和 version 分别输出混淆矩阵及 Precision/Recall/F1

#### Scenario: Quality score is not a classification metric
- **WHEN** LLM Judge 返回 `factual_consistency=0.4` 的连续质量分
- **THEN** 该分数不直接作为幻觉预测标签，也不改变 scoring 配置之外的分类指标口径
