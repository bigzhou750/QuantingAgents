## Purpose

该能力用于在评测平台之上建立受控自进化闭环，把失败样本、复核结论和评测指标转化为候选 Skill、Prompt、Policy、Rubric 和 Case 变更，并在验证通过后再生效。

## ADDED Requirements

### Requirement: Self-evolution shall be controlled by triggers
系统 SHALL 支持基于评测完成、趋势下滑、失败聚类、Bad Case 阈值和定时任务触发自进化候选流程。

#### Scenario: Trigger after evaluation regression
- **WHEN** 一个评测运行完成且核心指标低于配置阈值
- **THEN** 系统 SHALL 创建自进化候选任务或提示管理员创建候选任务

#### Scenario: Trigger from repeated bad cases
- **WHEN** 同一失败模式的 Bad Case 数量达到阈值
- **THEN** 系统 SHALL 将该模式作为候选优化输入

### Requirement: Proposal generation shall use bounded change surfaces
系统 SHALL 只允许候选变更作用于受控 artifact，包括 Skill、Prompt、routing policy、grounding policy、rubric 和 Case，并 MUST 禁止自进化流程直接修改核心代码、测试集、评分口径和样本切分。

#### Scenario: Candidate diff generation
- **WHEN** 系统生成候选变更
- **THEN** 候选 SHALL 包含目标 artifact、diff、原因、关联失败样本、影响面、预算和回滚方式

#### Scenario: Forbidden target
- **WHEN** 候选变更试图修改不在 allowlist 内的文件或资产
- **THEN** 系统 SHALL 拒绝该候选并记录拒绝原因

### Requirement: Verification shall replay candidates on isolated datasets
系统 SHALL 使用固定 dataset version、固定 scorer/rubric 版本和隔离验证集回放候选版本，并产出可比较的验证结果。

#### Scenario: Verify candidate
- **WHEN** 管理员或自动策略启动候选验证
- **THEN** 系统 SHALL 创建验证 run，并记录候选版本相对基线的 `pass@k`、`pass^k`、grounding、judge、延迟、成本和失败聚类变化

#### Scenario: Prevent test leakage
- **WHEN** 候选流程请求访问测试集或改变样本切分
- **THEN** 系统 SHALL 阻止该操作并标记为违反样本隔离

### Requirement: Promotion shall require approval or gate success
系统 SHALL 仅在人工审批或配置的 Release Gate 通过后，将候选 artifact 写回正式版本。

#### Scenario: Promote accepted candidate
- **WHEN** 候选验证通过且审批通过
- **THEN** 系统 SHALL 发布新的 artifact 版本，并保存验证结果、审批人、变更说明和 receipt

#### Scenario: Reject unsafe candidate
- **WHEN** 候选验证失败、成本超限、安全退化或新增高风险 regression
- **THEN** 系统 SHALL 禁止 promote，并保留失败候选用于复盘

### Requirement: Rollback shall restore stable versions
系统 SHALL 支持将 Skill、Prompt、Policy、Rubric 和 Case 回滚到上一个稳定版本，并记录回滚原因。

#### Scenario: Rollback promoted candidate
- **WHEN** 已生效候选导致线上或回归指标退化
- **THEN** 系统 SHALL 支持回滚到指定稳定版本，并生成回滚审计记录

### Requirement: Self-evolution workbench shall expose full lifecycle
系统 SHALL 提供自进化工作台，展示 trigger、proposal、verification、approval、promotion、rollback、artifact 版本和审计记录。

#### Scenario: Inspect proposal lifecycle
- **WHEN** 管理员打开自进化候选详情
- **THEN** 系统 SHALL 展示触发来源、失败模式、候选 diff、验证 run、门禁结果、审批记录和最终状态

### Requirement: Automation mode shall be configurable
系统 SHALL 支持 `manual`、`semi-auto` 和 `auto` 三种自动化模式，并在生产环境默认要求人工审批。

#### Scenario: Manual mode
- **WHEN** 自进化配置为 `manual`
- **THEN** 系统 SHALL 只生成分析和建议，不自动生成可应用 diff

#### Scenario: Semi-auto mode
- **WHEN** 自进化配置为 `semi-auto`
- **THEN** 系统 SHALL 允许生成候选 diff 和验证 run，但不得自动 promote
