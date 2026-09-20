## Purpose

定义 Vibe runtime 如何产出真实结构化决策事件，并把工具执行、证据获取和生命周期事件从决策链中正确分离，使审计页面能够展示可追溯的“输入到结论”链路，而不是把运行事件包装成决策记录。

## ADDED Requirements

### Requirement: Runtime must emit structured decision records

Vibe runtime 在每个关键决策节点 MUST 发出 `decision.record` 事件，并至少包含决策场景、候选方案、选中项、选择依据、最终结论、证据引用 ID、父决策 ID、决策状态、置信度、风险等级、模型/策略版本、task ID、session ID 和产生时间；发出的记录 MUST 能按 task 或 session 串联成完整决策链。

#### Scenario: Record a tool selection decision
- **WHEN** Agent 从多个可用工具中选择一个工具执行
- **THEN** runtime MUST 发出包含候选工具列表、选中工具、选择依据和父决策 ID 的 `decision.record` 事件

#### Scenario: Record entity resolution decision
- **WHEN** runtime 将用户描述或自然语言查询锁定到具体标的
- **THEN** runtime MUST 发出包含候选标的、最终标的选择、来源和锁定状态的结构化决策记录

#### Scenario: Record final research conclusion
- **WHEN** Agent 完成分析并生成最终研究结论
- **THEN** runtime MUST 发出包含依据证据、分析结论和风险等级的最终决策记录，且不得伪造缺失依据

#### Scenario: Runtime omits selection rationale
- **WHEN** 底层模型或运行链路没有提供选择理由
- **THEN** runtime MUST 将决策状态标记为 `unverified`，并记录选择理由缺失，不得静默生成解释

### Requirement: Tool execution must be linked as evidence, not decision

工具调用与工具结果 MUST 通过 `call_id` 关联为同一执行证据，MUST NOT 各自生成独立决策节点；只有引用该证据 ID 的 `decision.record` 才能成为决策链节点。

#### Scenario: Tool call and result share one evidence chain
- **WHEN** Agent 调用 `get_market_data` 并收到结果
- **THEN** 系统 MUST 将两次事件关联到同一个 `call_id`，并作为后续决策节点的证据引用

#### Scenario: Tool result has no decision record
- **WHEN** 工具执行成功但 runtime 没有发出对应决策节点
- **THEN** 审计页面 MUST 将该工具执行显示为证据/运行事件，不得显示为已确认决策

### Requirement: Lifecycle events must not become decisions

`attempt.started`、`attempt.completed`、`attempt.failed` 和 `attempt.cancelled` MUST 仅作为任务生命周期与最终输出事件处理，MUST NOT 生成结构化决策记录；任务完成时 MUST 保留最终输出，但不得把最终输出直接伪装成决策节点。

#### Scenario: Completed task keeps final output without false decision
- **WHEN** 一个任务完成且 runtime 没有发出最终决策事件
- **THEN** 系统 MUST 保存最终输出并显示任务已完成，但决策链 MUST 不包含由 `attempt.completed` 生成的决定性记录

#### Scenario: Failed task remains auditable
- **WHEN** 一个任务执行失败
- **THEN** 系统 MUST 保留运行事件、错误信息和已有证据，且不得生成伪造的“成功结论”决策节点

### Requirement: Missing data must be represented as evidence outcome

工具返回空数据、数据源报错、权限禁止或 Agent 未调用时，系统 MUST 将该结果记录为证据未获取或不可用，并 MUST 在决策依据中明确展示数据缺口；证据缺失 MUST NOT 被当作决策理由不足之外的事实结论。

#### Scenario: Data source returns empty result
- **WHEN** 工具返回空数组或空结果
- **THEN** 系统 MUST 记录该证据为 `unavailable`，后续决策可以引用该缺口，但不得声称已获取该数据

#### Scenario: Missing data is cited in final decision
- **WHEN** 最终结论依赖未获取的估值或财务数据
- **THEN** 决策记录 MUST 引用缺失证据状态并在结论依据中说明该缺口，避免把推断描述为已核实数据

### Requirement: Audit chain must display real decisions and explicit gaps

决策审计接口和页面 MUST 区分真实决策记录、运行事件、证据事件和缺失数据；当只有运行事件而没有 `decision.record` 时 MUST 显示为 `events_without_chain`，不得把工具调用和最终回答整理成完整决策链。

#### Scenario: Audit page shows real decision chain
- **WHEN** 任务包含多个真实 `decision.record`
- **THEN** 页面 MUST 按父子关系显示场景、候选、依据、证据、结论、状态和风险

#### Scenario: Audit page has only runtime events
- **WHEN** 任务只有工具事件和生命周期事件
- **THEN** 页面 MUST 明确提示尚无结构化决策链，并仅展示运行事件作为降级审计视图
