## Why

当前提案详情页虽然能显示目标 Skill 和变更摘要，但审批人无法确认“具体修改了哪个 Skill 的哪个 section、原内容是什么、候选内容是什么，以及发布后运行时实际会得到什么”。现有 diff 只保存摘要和影响区域，候选内容缺少可审计的 before/after 结构，容易造成误审批或无法排障。

## What Changes

- 为 Skill、Prompt、Policy、Rubric、Case 的候选变更补充结构化 before/after 内容。
- 为每个 section 或逻辑字段记录 `add`、`update`、`delete`、`unchanged` 等变更类型。
- 固化候选内容快照与变更明细之间的一致性校验，防止摘要和实际发布内容不一致。
- 在提案详情页增加“变更对象、变更 section、原内容、候选内容、最终发布内容、运行时文件”分层展示。
- 对历史提案中缺少 before/after 的数据显示明确的“历史 diff 不完整”状态，不从当前正式内容反推旧内容。
- 保留原始 diff JSON 作为排障入口，并支持复制或下载完整候选内容。

## Capabilities

### New Capabilities

- `evolution-proposal-release-content-diff`: 自进化提案必须提供可审计的结构化变更明细和实际发布内容预览。

### Modified Capabilities

- 无。现有提案详情页的展示改造作为本 change 新能力的一部分交付，不修改已归档的主 capability。

## Impact

- `app/services/evolution/proposal_service.py`：生成并保存结构化候选 diff。
- `app/services/evolution/verification_service.py`：验证候选快照与 diff 明细的一致性。
- `app/services/evolution/promote_service.py`：发布前校验内容明细，并在回执中记录发布内容摘要。
- `app/models/evolution.py`：补充变更明细和内容快照字段。
- `app/routers/evolution.py`：必要时暴露结构化发布内容接口；保持现有权限和 API 兼容。
- `frontend/src/views/Evolution/ProposalDetail.vue` 与相关 helper/test：重做发布内容交互。
- 不改变既有审批权限、验证门禁和 artifact 版本状态机。
