## Purpose

为 QuantingAgents 提供一个面向 Vibe Agent runtime 的生产级测评与治理能力，支持研发和管理员对 Agent 的答案质量、工具过程、证据链、安全边界、运行成本和版本回归进行持续验证。

## ADDED Requirements

### Requirement: Evaluation platform must manage versioned datasets and cases
系统 MUST 提供评测集、评测用例和版本管理能力，并且 MUST 能按数据集版本重放同一批 case。

#### Scenario: Create versioned dataset
- **WHEN** 研发或管理员创建评测集并录入多个评测用例
- **THEN** 系统保存数据集版本、case 内容、标签、参考答案和评分标准，并可按版本查询

#### Scenario: Replay a dataset version
- **WHEN** 用户选择某个数据集版本发起评测运行
- **THEN** 系统 MUST 对该版本下的全部 case 使用相同输入和评分标准进行重放

### Requirement: Evaluation platform must execute repeated trials for each case
系统 MUST 支持每个 case 进行一次或多次 trial 运行，并记录每次运行的独立结果。

#### Scenario: Run multiple trials
- **WHEN** 用户为同一 case 指定多次 trial
- **THEN** 系统 MUST 保存每次 trial 的输入、输出、状态、耗时、token、错误和最终判定

#### Scenario: Trial failure is preserved
- **WHEN** 某个 trial 超时、取消、失败或返回空结果
- **THEN** 系统 MUST 保留失败原因和相关 trace，且不得覆盖其他 trial 的结果

### Requirement: Evaluation platform must preserve standardized trace and replayability
系统 MUST 将 Vibe Agent runtime 的消息、LLM 调用、tool、skill、Swarm、证据、错误和最终结果保存为可回放的标准化 trace。

#### Scenario: Record structured trace
- **WHEN** Agent 执行研究任务
- **THEN** 系统 MUST 记录与该 trial 关联的结构化事件序列，并支持按事件游标查看

#### Scenario: Recover after interruption
- **WHEN** 页面刷新或服务重启后重新查看同一 trial
- **THEN** 系统 MUST 通过持久化 trace 恢复显示历史过程，而不是依赖浏览器内存

### Requirement: Evaluation platform must provide layered scoring
系统 MUST 提供分层评分能力，至少包括 outcome、trajectory、金融质量、证据质量、工具过程、安全治理和运行成本。

#### Scenario: Score a completed trial
- **WHEN** trial 完成后进入评分阶段
- **THEN** 系统 MUST 为该 trial 生成多维分数和可读原因说明

#### Scenario: Score unavailable due to missing evidence
- **WHEN** 某一评分维度缺少必要证据、trace 或输出结构
- **THEN** 系统 MUST 明确标记该维度不可评分或低置信，而不是伪造分数

### Requirement: Evaluation platform must support deterministic, judge-based, and human review scoring
系统 MUST 支持规则评分、LLM-as-judge 评分和人工复核，并 MUST 将评分来源、版本和覆盖关系持久化。

#### Scenario: Deterministic score check
- **WHEN** 评测需要检查 schema、权限、token、耗时、工具调用或格式约束
- **THEN** 系统 MUST 使用可重复的确定性规则给出结果

#### Scenario: Judge-based open-ended scoring
- **WHEN** 评测需要判断答案完整性、金融推理、证据相关性或风险披露
- **THEN** 系统 MUST 允许使用固定版本的 LLM-as-judge，并保存 rubric、judge model 和输出

#### Scenario: Human review overrides score
- **WHEN** 管理员对低置信、高风险或边界样本进行人工复核
- **THEN** 系统 MUST 记录人工覆盖结果、复核人和原因，并保留原始评分

### Requirement: Evaluation platform must compute stability and regression metrics
系统 MUST 提供 pass@k、pass^k、方差、成功率、失败率、成本、延迟和 token 使用等稳定性和回归指标。

#### Scenario: Compute stability metrics
- **WHEN** 同一 case 运行多个 trial
- **THEN** 系统 MUST 汇总这些 trial 的稳定性指标并可按版本对比

#### Scenario: Compare two versions
- **WHEN** 用户选择两个不同 Agent 配置或版本
- **THEN** 系统 MUST 显示各维度指标差异和失败样本差异

### Requirement: Evaluation platform must support bad case feedback loop
系统 MUST 支持将线上失败、人工复核失败、安全拦截和用户反馈样本回流为新的评测用例或 bad case。

#### Scenario: Convert a failure into a bad case
- **WHEN** 某个 trial 经过复核被判定为失败或高风险
- **THEN** 系统 MUST 允许将其转存为可版本化的 bad case 并附带标签

#### Scenario: Reuse a bad case in regression
- **WHEN** 研发将 bad case 加入回归集
- **THEN** 系统 MUST 在后续运行中保留其历史来源和标签

### Requirement: Evaluation platform must expose an internal management UI
系统 MUST 提供仅供研发和管理员使用的后台页面，用于管理评测集、发起运行、查看指标、回放 trace、复核分数和查看 bad case。

#### Scenario: Access evaluation UI
- **WHEN** 认证用户不具备研发或管理员权限
- **THEN** 系统 MUST 拒绝访问评测后台页面和相关 API

#### Scenario: View trial details
- **WHEN** 研发或管理员打开某个 trial
- **THEN** 页面 MUST 显示输入、输出、trace、分数、失败原因和复核状态

### Requirement: Evaluation platform must preserve existing product workflows
系统 MUST 不改变现有单股分析、批量分析、任务中心和自然语言研究工作台的既有行为契约。

#### Scenario: Existing analysis stays unchanged
- **WHEN** 用户提交现有单股分析或批量分析任务
- **THEN** 请求 MUST 继续进入原有链路，不经过评测平台

#### Scenario: Evaluation failures are isolated
- **WHEN** 评测平台或评测任务失败
- **THEN** 现有研究工作台和分析流程 MUST 仍可独立运行

