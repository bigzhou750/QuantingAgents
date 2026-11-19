## Purpose

该能力用于把现有 Agent 评测平台补齐为生产级后台工作台，使管理员能够完成数据集管理、评测运行、结果分析、人工复核、bad case 回流、趋势观察、报告留档和发布门禁。

## ADDED Requirements

### Requirement: Dataset management shall support production case operations
系统 SHALL 在评测集详情中支持 Case 新增、查看、编辑、删除、批量导入、批量编辑、版本发布和空数据引导。

#### Scenario: Empty dataset guidance
- **WHEN** 管理员打开没有 Case 的评测集
- **THEN** 系统 SHALL 展示添加 Case、导入 Golden Set、批量导入和从 Bad Case 回流的入口

#### Scenario: Case version update
- **WHEN** 管理员新增、编辑、删除或回流 Case
- **THEN** 系统 SHALL 更新评测集版本并保留可复现的 Case 版本关系

### Requirement: Evaluation run detail shall expose final output and metrics
系统 SHALL 在评测运行详情中展示 run 摘要、trial 列表、每个 trial 的输入、最终输出、错误、trace、评分、人工复核状态、token、成本、延迟、`pass@k` 和 `pass^k`。

#### Scenario: Inspect failed trial
- **WHEN** 管理员从运行详情打开失败 trial
- **THEN** 系统 SHALL 在同一视图展示输入、最终输出、失败原因、评分原因、证据引用和 trace 入口

#### Scenario: Multi-trial metrics
- **WHEN** 一个 run 的 `num_trials` 大于 1
- **THEN** 系统 SHALL 展示 `pass@k`、`pass^k` 和每个 Case 的稳定性明细

### Requirement: Reports shall be reviewable and exportable
系统 SHALL 为每个评测运行提供报告页，包含运行配置、数据集版本、聚合指标、评分汇总、失败聚类、成本、延迟、人工复核结果和导出入口。

#### Scenario: View run report
- **WHEN** 管理员打开一个已完成 run 的报告页
- **THEN** 系统 SHALL 展示可留档的完整报告，并提供回到 run、trial、case 和 bad case 的跳转

### Requirement: Human review shall be evidence-aware
系统 SHALL 在人工复核中展示评分结论、维度理由、原始 judge 输出、证据引用、Case 输入、Agent 输出、trace 证据和历史评分，并允许复核后标记通过/失败、调整分数、写复核意见和回流 Bad Case。

#### Scenario: Review judge finding
- **WHEN** 复核人打开一条 `llm_judge` 待复核项
- **THEN** 系统 SHALL 展示 judge 原始输出、分维度 reason、Agent 最终输出、证据引用和 trace 入口

#### Scenario: Convert reviewed failure
- **WHEN** 复核人确认一条失败样本需要回归覆盖
- **THEN** 系统 SHALL 支持将该样本加入 Bad Case 池或回流到指定评测集

### Requirement: Scorer configuration shall be explicit
系统 SHALL 允许管理员在创建评测运行时选择评分器、配置 judge model、配置 rubric 版本、配置低置信阈值和复核策略，并 SHALL 将未启用或未安装的评分器标记为 `skipped` 或 `not_configured`。

#### Scenario: Missing optional scorer
- **WHEN** DeepEval、Ragas 或 Promptfoo 未安装或未启用
- **THEN** 系统 SHALL 将对应评分结果标记为 `skipped` 或 `not_configured`，并不得把它作为真实低分进入待复核队列

### Requirement: Grounding shall map claims to evidence
系统 SHALL 支持把最终输出拆解为 claim，并为每条 claim 记录证据引用、证据片段、来源、trace 事件、判定结果和理由。

#### Scenario: Unsupported claim
- **WHEN** 某条 claim 无法在 trace 或引用证据中找到支撑
- **THEN** 系统 SHALL 将该 claim 标记为 `unsupported`，并展示到复核页和报告页

#### Scenario: Contradicted claim
- **WHEN** 某条 claim 与可用证据冲突
- **THEN** 系统 SHALL 将该 claim 标记为 `contradicted`，并保留冲突证据

### Requirement: Trends and comparisons shall support drill-down
系统 SHALL 在质量趋势和运行对比中展示成功率、失败率、评分维度、`pass@k`、`pass^k`、延迟、成本、失败聚类和阈值说明，并支持下钻到 run、trial、case、score 和 bad case。

#### Scenario: Drill down from trend regression
- **WHEN** 管理员发现某次趋势下滑
- **THEN** 系统 SHALL 支持从趋势点跳转到对应 run，并进一步定位相关 trial 和失败聚类

### Requirement: Production governance shall be configurable
系统 SHALL 支持 Release Gate、定时回归、线上抽样、数据快照、成本预算、告警订阅和第三方观测配置，并保留审计记录。

#### Scenario: Release gate blocks regression
- **WHEN** 一个 run 未达到配置的成功率、`pass@k`、grounding、安全或成本阈值
- **THEN** 系统 SHALL 标记 gate 未通过，并展示阻断原因
