## Purpose

为 Agent 输出提供基于 Claim-Evidence 真值标注的幻觉检测指标，使检测结果可复现、可解释，并能区分证据不足、证据矛盾和正常回答。

## ADDED Requirements

### Requirement: Claim truth annotation

评测系统 MUST 支持为每条 Claim 保存人工或复核后的真值标签、幻觉类型、证据引用、标注来源和标注版本。未完成真值标注的 Claim MUST NOT 参与 Recall、Precision 或 F1 计算。

#### Scenario: Save a labeled claim
- **WHEN** 评测人员提交 Claim 的 `supported`、`unsupported` 或 `contradicted` 标签及其证据依据
- **THEN** 系统保存标签、标注信息和版本，并允许后续评分使用该 Claim

#### Scenario: Exclude unlabeled claim
- **WHEN** 评测运行包含没有人工真值标签的 Claim
- **THEN** 系统保留该 Claim 的现有证据评分，但不将其纳入分类指标分母，并明确返回样本缺少真值

### Requirement: Hallucination prediction

系统 MUST 基于现有证据判定生成可复现的二分类幻觉预测，并保留预测标签、判定阈值、评分器版本和判定原因。`unsupported` 或 `contradicted` 的 Claim MUST 可按配置映射为幻觉预测。

#### Scenario: Predict hallucination from unsupported claim
- **WHEN** Claim-Evidence 评分将 Claim 判定为 `unsupported` 或 `contradicted`
- **THEN** 系统按当前评测配置生成 `hallucinated` 预测，并记录对应证据匹配信息

#### Scenario: Preserve weak support
- **WHEN** Claim 被判定为 `weakly_supported`
- **THEN** 系统 MUST 按评测配置将其视为幻觉、非幻觉或排除项之一，且在指标结果中展示该口径

### Requirement: Classification metrics

系统 MUST 按 Claim 聚合 TP、FP、FN、TN，并计算 Recall、Precision 和 F1；结果 MUST 返回各指标的分子、分母、参与样本数和零分母处理状态。

#### Scenario: Calculate metrics with labeled claims
- **WHEN** 评测运行同时存在人工真值和系统预测
- **THEN** 系统返回混淆矩阵及 `Recall = TP/(TP+FN)`、`Precision = TP/(TP+FP)` 和对应 F1 结果

#### Scenario: Handle no positive samples
- **WHEN** 评测集没有真实幻觉 Claim 或系统没有预测幻觉 Claim
- **THEN** 系统不抛出除零错误，并将相关指标标记为 `undefined` 或按统一约定返回空值及原因

### Requirement: Metric breakdown and auditability

系统 MUST 支持按幻觉类型和数据集版本聚合指标，并能追溯到参与计算的 Claim、原始回答和证据。指标结果 MUST 包含评测集版本、评分器版本和标签口径。

#### Scenario: Inspect metric breakdown
- **WHEN** 用户查看一次评测的幻觉指标
- **THEN** 系统展示总体指标、按类型指标、样本量和口径，并可下钻到对应 Claim 及证据

#### Scenario: Reproduce a prior run
- **WHEN** 用户使用相同数据集版本、标签版本和评分器版本重新查看历史结果
- **THEN** 系统返回与原运行一致的混淆矩阵和分类指标
