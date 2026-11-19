## Purpose

为 Agent 决策审计页面提供可区分的审计链状态、真实事件降级查看、稳定分页和可读中文事件名称，让运维人员能定位是数据缺失、关联错误还是未生成结构化链。

## ADDED Requirements

### Requirement: Audit chain status must distinguish data availability
决策审计接口 MUST 返回可区分的 `complete`、`partial`、`events_without_chain` 和 `empty` 状态，并 MUST 返回 task ID、session ID、运行事件数、trace 数、结构化决策记录数、解释/校验/复核数量和查询范围，不得只返回单一布尔值表示“有无结构化决策链”。

#### Scenario: Only runtime events exist
- **WHEN** 查询标识存在运行事件、trace 或日志，但没有 `decision_records`
- **THEN** 接口 MUST 返回 `events_without_chain`，并提供各类数据数量与查询范围

#### Scenario: No audit data exists
- **WHEN** 查询标识无法定位任何任务、会话或审计数据
- **THEN** 接口 MUST 返回 `empty`，并明确说明没有找到相关审计数据

#### Scenario: Decision records exist with partial context
- **WHEN** 存在 `decision_records` 但解释、校验、复核或最终输出关联不完整
- **THEN** 接口 MUST 返回 `partial`，并列出缺失或不可用的关联类型

### Requirement: Audit events must be paginated with stable ordering and permission control
系统 MUST 提供 `GET /api/decision-audit/chains/{identifier}/events` 后端分页接口，参数至少包含 `scope`、`page` 和 `page_size`，返回 `items`、`page`、`page_size`、`total` 和 `has_more`；分页排序 MUST 基于稳定事件序号或创建时间，并 MUST 沿用现有权限校验和 task/session 查询范围。

#### Scenario: Load first page of events
- **WHEN** 管理员请求 `page=1&page_size=20`，且共有 86 条事件
- **THEN** 接口 MUST 返回 20 条事件、`total=86` 和 `has_more=true`

#### Scenario: Unauthorized user requests events
- **WHEN** 无权限用户调用事件分页接口
- **THEN** 系统 MUST 拒绝访问，且不得泄露任务、会话或事件内容

### Requirement: Event display names must be readable and phase-aware
决策审计页面对运行事件 MUST 显示中文名称，MUST 同时识别 `event_type` 与 payload 中的 `phase`；`tool_call + phase=tool_result` 等同工具返回事件；未知事件 MUST 保留原始名称，避免映射缺失导致审计信息不可读。

#### Scenario: Tool result is encoded in payload phase
- **WHEN** 事件为 `event_type=tool_call` 且 `payload.phase=tool_result`
- **THEN** 页面 MUST 将事件显示为“工具返回”

#### Scenario: Unknown event type
- **WHEN** 事件类型不在已知映射表中
- **THEN** 页面 MUST 显示原始事件名称，并保留事件原始内容

### Requirement: Degraded audit view must not masquerade as complete decision chain
当审计状态为 `events_without_chain` 时，页面 MUST 明确显示“本次对话存在运行事件，但尚未生成结构化决策链”，MUST 展示原始运行事件作为降级审计视图，并 MUST 同时展示 task/session ID、各类数据数量和查询范围；原始事件 MUST NOT 被标记为完整结构化决策链。

#### Scenario: Admin opens event-only audit page
- **WHEN** 管理员打开一个只有运行事件、没有结构化决策记录的审计页面
- **THEN** 页面 MUST 展示降级提示和原始事件列表，且不得声称已具备完整决策可追溯性

#### Scenario: Decision records exist but UI hides them
- **WHEN** `decision_records` 已存在但因关联字段或查询范围没有命中
- **THEN** 页面 MUST 显示 `events_without_chain` 或明确的关联异常提示，并展示 task/session 关联字段以便定位 bug
