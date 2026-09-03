## Context

现有 `EvidenceQualityScorer` 已完成 Claim 抽取、证据匹配和 `supported/weakly_supported/unsupported/contradicted` 判定；评测模型中也已有 Claim-Evidence 结构和 evidence score 聚合。当前缺少人工真值与预测标签的明确分离，因此无法得到可解释的分类指标。

## Goals / Non-Goals

**Goals:**

- 在现有证据评分结果上增加 Claim 级真值、预测和分类指标。
- 保持历史评分结果可读，不把缺失真值误报为低质量指标。
- 让结果能够按版本、类型和 Claim 下钻复核。

**Non-Goals:**

- 不重写现有 n-gram 证据匹配算法。
- 不把 Ragas 的连续分数直接转换为 Recall/F1。
- 不新增独立的在线拦截流程或改变普通 Agent 输出链路。

## Decisions

### 1. Extend existing ClaimEvidence

在现有 `ClaimEvidence` 上增加真值和预测所需字段，保留现有 `verdict` 作为评分器判定，新增字段区分人工真值与系统预测，避免把 scorer 的 verdict 当作 ground truth。

候选字段包括 `truth_label`、`truth_source`、`hallucination_type`、`prediction_label`、`prediction_reason` 和 `label_version`。旧记录缺少这些字段时按未标注处理。

### 2. Define hallucination mapping explicitly

默认将 `unsupported`、`contradicted` 映射为幻觉，将 `supported` 映射为非幻觉；`weakly_supported` 由评测配置决定，默认排除并单独统计，避免阈值争议污染主指标。

### 3. Add pure metric aggregation

在评测服务层增加纯函数式聚合逻辑：输入 Claim 的 truth/prediction 列表，输出混淆矩阵和指标。指标计算不依赖数据库或模型，便于单元测试、历史重算和边界验证。

### 4. Keep Ragas separate

Ragas 的 Faithfulness 和 Answer Relevancy 继续作为连续质量分数保存；不与 Claim 分类指标混合。报告层可并列展示，但必须标识不同的计算口径。

### 5. Version the evaluation contract

聚合结果保存数据集版本、标签版本、预测规则版本和 scorer 版本。若真值缺失、版本不完整或正类样本为零，结果返回可解释状态，不填充虚假的 0 分。

## Risks / Trade-offs

- [Risk] 句子级 Claim 抽取可能合并多个事实 → [Mitigation] 保留当前抽取结果，支持人工拆分或标记不可评估 Claim。
- [Risk] n-gram 匹配会把表述相近但事实错误的 Claim 判为 supported → [Mitigation] 将其保留为检测器预测，使用人工真值衡量误报和漏报，不宣称匹配结果等于事实真值。
- [Risk] 标签不一致影响指标 → [Mitigation] 强制记录标注来源、标签版本和口径，并对抽样样本进行复核。
- [Risk] 历史数据缺少标签 → [Mitigation] 保留 evidence score，幻觉分类指标显示 not available。

## Migration Plan

1. 以可选字段方式扩展 Claim 和 Score 数据结构。
2. 为新评测集提供 Claim 标注入口或导入格式。
3. 增加预测映射和纯指标聚合，先通过 API/报告返回结果。
4. 对历史运行仅展示已有 evidence/Ragas 结果，不回填未经标注的幻觉指标。
5. 若新指标异常，可关闭指标展示或回退到旧 evidence score，不影响 Agent 主流程。
