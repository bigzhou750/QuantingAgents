## Purpose

这个能力用于让自进化提案详情页从“堆信息的管理页”变成“可快速判断下一步动作的决策页”，让审批人一眼看懂提案当前状态、变更意图、验证结论和发布条件。

## ADDED Requirements

### Requirement: Proposal detail page must present a decision-oriented summary
提案详情页 SHALL 以结构化摘要展示提案的核心决策信息，包括提案 ID、状态、触发类型、风险等级、目标 Artifact、正式基线版本、候选版本和发布就绪状态。

#### Scenario: View a loaded proposal
- **WHEN** 研发或管理员打开某个提案详情页
- **THEN** 页面 SHALL 首屏显示该提案的核心摘要，并且无需展开原始 JSON 就能判断当前状态和下一步动作

#### Scenario: Proposal is still waiting for verification
- **WHEN** 提案尚未完成验证
- **THEN** 页面 SHALL 明确标记其仍处于待验证或验证中状态，并 SHALL 不把“已可发布”误显示为当前状态

### Requirement: Proposal detail page must render change and comparison data in readable form
提案详情页 SHALL 将变更描述、影响区域和指标对比以结构化方式展示，并 SHALL 将原始 JSON 作为辅助信息而不是主信息。

#### Scenario: Proposal has a diff payload
- **WHEN** 提案包含 `diff` 内容
- **THEN** 页面 SHALL 显示变更描述、受影响区域和关键信息摘要，并且 SHALL 允许用户展开查看完整原始内容

#### Scenario: Verification result contains comparison metrics
- **WHEN** 验证结果包含对比指标或分维度评分
- **THEN** 页面 SHALL 用可读的分组、标签或卡片展示这些指标，而不是只显示一大段未经解释的 JSON

### Requirement: Proposal detail page must explain missing or unavailable data explicitly
提案详情页 SHALL 对验证记录、审批记录、回执或对比结果的缺失提供明确空态说明，且 SHALL 说明当前缺失属于“尚未生成”“尚未执行”还是“无可用数据”。

#### Scenario: Approval records do not exist yet
- **WHEN** 某个提案尚未进入审批阶段
- **THEN** 页面 SHALL 显示审批记录为空的原因或阶段说明，而不是只显示空白占位

#### Scenario: Verification run has not been created
- **WHEN** 提案仍未启动验证
- **THEN** 页面 SHALL 明确说明验证结果暂不可用，并 SHALL 保留后续刷新入口

### Requirement: Proposal detail page must keep actions status-aware and safe
提案详情页 SHALL 只在满足当前状态和门禁条件时显示可执行动作，并 SHALL 阻止用户对不满足条件的提案执行验证、批准、发布或停止操作。

#### Scenario: Forbidden target is opened
- **WHEN** 提案目标被标记为禁止修改
- **THEN** 页面 SHALL 禁用或隐藏验证与发布类操作，并 SHALL 显示禁止原因

#### Scenario: Gate failed verification is loaded
- **WHEN** 验证门禁未通过
- **THEN** 页面 SHALL 不允许直接进入发布动作，并 SHALL 明确提示阻断原因
