## Purpose

这个能力用于让自进化提案在进入批准或发布前，完整说明目标 artifact 的具体变更、原始内容、候选内容和最终 materialization，避免只凭摘要进行不可逆的正式发布。

## ADDED Requirements

### Requirement: Proposal SHALL preserve an auditable structured content diff

提案 SHALL 为每个候选 artifact 保存可审计的结构化变更明细，包括 artifact 标识、类型、源版本、候选版本、变更操作、影响 section 或逻辑字段，以及每个变更单元的 `before`、`after` 和必要的 unified diff。

#### Scenario: Skill section is updated

- **WHEN** 一个 Skill 的 `tool_selection` section 被候选修改
- **THEN** 提案 SHALL 明确记录目标 Skill、`tool_selection`、操作类型为 `update`、正式源版本、原内容和候选内容

#### Scenario: New section is added

- **WHEN** 候选新增一个正式版本不存在的 section
- **THEN** 变更明细 SHALL 将操作标记为 `add`，原内容 SHALL 明确为空或不存在，候选内容 SHALL 可直接查看

#### Scenario: Section is removed

- **WHEN** 候选删除一个原有 section
- **THEN** 变更明细 SHALL 将操作标记为 `delete`，并 SHALL 保留被删除的原内容

### Requirement: Candidate snapshot and structured diff SHALL be consistent

系统 SHALL 校验结构化 diff 与完整候选快照来自同一源版本，且每个变更单元的 `after` 内容能够在候选快照中定位；校验失败时 SHALL 阻止批准和发布。

#### Scenario: Candidate content matches diff

- **WHEN** 候选快照能够由源版本和全部变更单元重建
- **THEN** 系统 SHALL 将内容一致性标记为通过，并允许进入既有验证门禁

#### Scenario: Candidate content does not match diff

- **WHEN** 候选快照与任一变更单元的 `after` 内容不一致
- **THEN** 系统 SHALL 标记内容校验失败，说明不一致位置，并 SHALL 阻止批准或发布

#### Scenario: Historical proposal lacks structured diff

- **WHEN** 历史提案只有摘要而没有 before/after 明细
- **THEN** 系统 SHALL 标记“历史 diff 不完整”，并 SHALL 不从当前正式内容反推原内容

### Requirement: Release confirmation SHALL show actual publish content

提案详情页 SHALL 在发布操作附近展示实际发布对象、类型、源版本、候选版本、变更 section、内容摘要、完整候选内容和 runtime materialization 文件；原始 JSON SHALL 作为辅助入口保留。

#### Scenario: Operator reviews a Skill release

- **WHEN** 管理员查看一个可发布的 Skill 提案
- **THEN** 页面 SHALL 让管理员无需查看原始 JSON 即确认“改了哪个 Skill 的哪一部分、原内容是什么、候选内容是什么、发布到哪里”

#### Scenario: Release content is incomplete

- **WHEN** 提案缺少候选快照、before/after 明细或 materialization 目标
- **THEN** 页面 SHALL 显示缺失原因，且发布动作 SHALL 处于禁用状态

#### Scenario: Operator expands full content

- **WHEN** 管理员展开完整候选内容或原始 diff
- **THEN** 页面 SHALL 显示不截断的候选内容或原始数据，并 SHALL 不改变当前正式版本
