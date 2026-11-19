## Purpose

让管理员在自进化模块内通过独立页面查看已发布回执、提交发布后质量观测、读取质量结论和系统生成的后续动作，避免只能调用后端 API。

## ADDED Requirements

### Requirement: Post-release observation must be a standalone self-evolution page
系统 MUST 在自进化模块下提供独立“发布后观测”页面，路由使用 `/evolution/observation`，不合并进“进化回执”或“Artifact 管理”页面，并 MUST 通过侧边栏入口可发现和访问。

#### Scenario: Admin opens post-release observation
- **WHEN** 具备自进化管理权限的管理员点击“发布后观测”菜单
- **THEN** 页面 MUST 加载已发布回执列表和后续动作列表，并在页面内完成发布后观测流程

#### Scenario: Unauthorized user opens page
- **WHEN** 普通用户直接访问 `/evolution/observation`
- **THEN** 系统 MUST 拒绝访问并沿用现有权限边界

### Requirement: Page must support manual observation submission for a receipt
页面 MUST 允许管理员从已发布回执列表选择 `receipt_id`，填写 `success_rate`、`safety`、`evidence_quality`、`latency mean_ms` 和 `cost total_usd`，提交后 MUST 展示是否通过、失败检查项、是否建议回滚和本次生成的后续动作。

#### Scenario: Submit successful observation
- **WHEN** 管理员选择有效回执并提交阈值内的指标
- **THEN** 页面 MUST 展示通过结论及本次生成的后续动作，并刷新后续动作列表

#### Scenario: Submit failing observation
- **WHEN** 管理员提交某一项指标触发回滚或 Bad Case 建议
- **THEN** 页面 MUST 展示失败检查项、建议动作和对应链接，且不自动执行回滚

### Requirement: Follow-up actions must be readable and read-only in MVP
页面 MUST 展示 `GET /api/evolution/follow-up-actions` 返回的 `action_id`、`action_type`、`severity`、`escalation_level`、`status`、`artifact_id`、`receipt_id`、`proposal_id` 和 `created_at` 等字段，MUST 高亮 `pending` 动作，并 MUST 提供关联提案和回执的详情跳转；第一版 MUST NOT 在页面直接执行 rollback、stop 或动作状态更新。

#### Scenario: Pending follow-up action is highlighted
- **WHEN** 后续动作列表中包含 `status=pending` 的 rollback 或 bad_case 候选
- **THEN** 页面 MUST 高亮该动作并允许跳转到关联提案、回执或 Artifact 详情

#### Scenario: User tries to execute rollback from page
- **WHEN** 管理员在第一版页面尝试执行回滚或 stop
- **THEN** 页面 MUST NOT 提供可用执行入口，并告知回滚仍使用现有 Artifact 管理能力

### Requirement: Post-release observation page must keep backend compatible
第一版页面 MUST 复用现有 `POST /api/evolution/post-release/observe` 和 `GET /api/evolution/follow-up-actions` 接口，MUST NOT 改变后端接口契约；后端不可用或返回错误时 MUST 展示可读错误，且不得影响现有提案、回执和 Artifact 页面。

#### Scenario: Backend returns an error
- **WHEN** 观测指标提交或后续动作加载失败
- **THEN** 页面 MUST 展示失败原因并保持当前表单或列表状态，不跳转、不清空已有数据

#### Scenario: Existing evolution pages remain unchanged
- **WHEN** 管理员继续使用现有回执或 Artifact 管理页面
- **THEN** 页面行为和接口 MUST 与变更前保持一致
