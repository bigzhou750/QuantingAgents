## ADDED Requirements

### Requirement: Evaluation case ground truth must be pinned in run snapshots

评测平台 MUST 将 Case 上可选的真值数据（如 `gold_claims` 和负样本幻觉断言）纳入数据集版本和 run snapshot 管理。运行创建后，后续修改或删除这些真值 MUST NOT 影响已创建 Run 的指标计算。

#### Scenario: Run uses snapshot ground truth
- **WHEN** 用户基于包含真值的 Case 创建 Run，并在 Run 创建后修改 Case 真值
- **THEN** 该 Run 的评分和指标继续使用创建时固化的真值版本

#### Scenario: Legacy case has no ground truth
- **WHEN** 历史 Case 没有 `gold_claims` 或等价真值字段
- **THEN** 系统保持旧版 Case 可用，指标明确返回真值缺失状态，而不是拒绝整个 Run

### Requirement: Review strategy must be observable and coverage-aware

评测系统 MUST 让 `review_strategy` 真正影响待复核与 Claim 标注队列：支持 `auto`、`manual` 和 `all` 策略，并在 Run 和指标结果中展示实际使用的策略。任何抽样或低置信度优先的复核结果 MUST 在指标中标记为子集口径，不能默认视为全集真实指标。

#### Scenario: Auto strategy selects low-confidence claims
- **WHEN** Run 配置为 `auto` 且存在低置信度 Claim
- **THEN** 待标注队列优先展示低置信度或低分 Claim，并在结果中声明样本选择策略

#### Scenario: All strategy requires complete labeling
- **WHEN** Run 配置为 `all`
- **THEN** 幻觉指标只在该 Run 的所有 eligible Claim 完成标注后输出可用 Precision/Recall/F1
