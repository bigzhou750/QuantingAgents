## Purpose

为幻觉检测提供可复用、可审计的 Claim 级真值：支持数据集预置、批量导入、人工标注和覆盖率统计，使离线评测集能稳定产出 Precision/Recall/F1。

## ADDED Requirements

### Requirement: Dataset gold claims must be structured and snapshot-stable

评测系统 MUST 支持在 `EvalCase` 上保存可选 `gold_claims` 真值列表。每个真值条目 MUST 包含 Claim 原文、`truth_label`、`label_version`，并 SHOULD 包含 `hallucination_type`、`evidence_refs` 和真值来源。运行创建时 MUST 将 `gold_claims` 和等价负样本断言固化到 run snapshot，后续指标计算 MUST 使用该快照。

#### Scenario: Create a case with gold claims
- **WHEN** 评测人员为 Case 保存 `gold_claims`，其中包含支持的 Claim 和幻觉 Claim
- **THEN** 系统保存每条真值及其标签版本、幻觉类型和证据引用

#### Scenario: Run snapshot freezes gold claims
- **WHEN** 用户基于已配置 `gold_claims` 的 Case 创建评测 Run
- **THEN** Run snapshot 保存该版本的真值，后续 Case 被修改时，Run 仍使用快照中的真值计算指标

### Requirement: Batch truth import must support existing claim results

评测系统 MUST 支持按 `score_id` 和 `claim_id` 批量导入人工真值。导入结果 MUST 返回成功数、跳过数、失败数和每条失败原因；导入操作 MUST 只更新 `truth_label`、`truth_source`、`hallucination_type`、`evidence_refs`、`label_version` 和标注历史，不得覆盖系统预测 `prediction_label`。

#### Scenario: Import labels from file
- **WHEN** 评测人员提交包含多条 `score_id + claim_id + truth_label` 的批量标注文件
- **THEN** 系统逐条写入真值并返回导入汇总，已标注 Claim 可以立即进入指标计算

#### Scenario: Import contains invalid target
- **WHEN** 批量文件中存在不存在的 `score_id` 或 `claim_id`
- **THEN** 系统跳过该条并返回明确失败原因，不中断其余条目

### Requirement: Claim review workflow must support direct annotation

人工复核页面 MUST 允许复核人直接为 Claim 选择 `supported`、`unsupported`、`contradicted` 或 `excluded`，填写幻觉类型、证据引用和 `label_version`；每次保存 MUST 记录复核人、时间和标注历史。标注队列 MUST 支持全量标注、低置信度/低分优先和抽样标注三种策略，并展示当前策略。

#### Scenario: Annotate a claim in review UI
- **WHEN** 复核人在人工复核页面对一条 Claim 提交真值标签
- **THEN** 系统保存该标注并追加到 `annotation_history`

#### Scenario: Sample review strategy
- **WHEN** Run 配置使用抽样标注策略
- **THEN** 系统按可复现抽样规则选择需要人工标注的 Claim，并在指标中标识该采样口径

### Requirement: Metrics must expose label coverage

幻觉指标 MUST 返回已标注 Claim 数、未标注 Claim 数、参与指标 Claim 数、排除 Claim 数和标注覆盖率。真实 `precision`、`recall`、`f1` MUST 仅在达到配置的最小覆盖率且存在可计算分母时返回；否则 MUST 返回 `not_available` 并说明原因。

#### Scenario: Partial labels are visible
- **WHEN** 一个 Run 只有部分 Claim 被人工标注
- **THEN** 指标接口返回标注覆盖率和 not_available 状态，不得把部分标注结果伪装成全量指标

#### Scenario: Full labels produce metrics
- **WHEN** Run 的全部 eligible Claim 已标注且存在系统预测
- **THEN** 系统返回 Precision、Recall、F1、混淆矩阵和元数据
