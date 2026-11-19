## ADDED Requirements

### Requirement: Evaluation trace must preserve decision records

评测平台 MUST 在标准化 trace 中保存 `decision` 事件和决策记录引用，并 MUST 支持按 trial 查询决策链、决策节点状态和解释校验结果；历史 trial 缺少决策事件时 MUST 标记为 `legacy_unverified`，不得伪造决策链。

#### Scenario: Trial contains decision records
- **WHEN** 评测 trial 运行的 Agent 生成了结构化决策链
- **THEN** 系统 MUST 在 trial trace 中保存决策事件，并允许从 trial 详情跳转到决策链

#### Scenario: Trial predates decision records
- **WHEN** 用户查看旧 trial，其 trace 中没有决策事件
- **THEN** 系统 MUST 继续显示原有 trace，并将决策链和解释校验区域标记为不可用

### Requirement: Evaluation trial details must expose explainability results

评测运行详情 MUST 展示 trial 的决策节点、候选选项、证据关联、解释分层、解释校验状态和复核状态；当某维度不可用时 MUST 明确说明缺失原因。

#### Scenario: Admin reviews a trial
- **WHEN** 管理员打开包含决策链的 trial
- **THEN** 页面 MUST 展示决策路径、证据下钻、解释一致性状态和是否进入人工复核

#### Scenario: Scorer has no explanation input
- **WHEN** 评分器因缺少决策记录或解释校验结果而无法评分
- **THEN** 系统 MUST 将对应评分状态标记为 `not_configured`、`skipped` 或 `error`，不得作为低分样本误导复核

### Requirement: Bad cases and online samples must retain audit references

Bad Case 和线上抽样记录 MUST 保留 `business_id`、`task_id`、`session_id`、决策链引用和解释校验结果，使失败样本可以回到线上审计链或评测集继续追溯。

#### Scenario: Convert a live failure into bad case
- **WHEN** 线上任务被标记为失败或解释不一致并转为 Bad Case
- **THEN** 系统 MUST 保存业务、任务、会话和决策链引用，并允许通过引用查看完整审计链

#### Scenario: Online sample has no decision reference
- **WHEN** 线上抽样来自旧版本且没有决策链引用
- **THEN** 系统 MUST 保存已有输入、输出和失败原因，并标记决策链引用缺失
