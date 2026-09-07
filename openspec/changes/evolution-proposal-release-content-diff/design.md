## Context

See proposal.md - Why. 当前提案 diff 主要由摘要、影响区域和候选快照组成，验证阶段还会追加通用内容，导致发布审批无法建立可靠的 before/after 证据链。

## Goals / Non-Goals

**Goals:**

- 让候选内容变更以结构化、可审计的数据保存。
- 让 Skill、Prompt、Policy、Rubric、Case 共用变更单元模型，同时允许 Skill 使用 section 级文本 diff。
- 在批准和发布前校验 diff、源版本和候选快照的一致性。
- 让详情页以“对象 → 变更单元 → 最终快照 → materialization 目标”的顺序支持审批。

**Non-Goals:**

- 不改变既有提案状态机、审批权限和发布门禁语义。
- 不为历史提案伪造无法恢复的 before 内容。
- 不在本 change 中引入新的 diff 算法依赖或外部代码托管服务。

## Decisions

- 在现有 `diff` 中增加稳定的 `artifact_id`、`source_version`、`operation` 和 `changes` 字段，并保留旧字段兼容读取；这样可以渐进迁移已有提案。
- 以结构化变更单元作为审批事实，以 `candidate_snapshot` 作为最终发布事实；发布前通过重建或定位校验确保两者一致。
- 对 Skill 使用 section 级文本 before/after 和 unified diff，对其他 artifact 使用逻辑字段或结构化 JSON 路径；避免强行把所有类型都转换成 Markdown 文本。
- 页面使用独立的变更分组和内容折叠区，不把完整内容默认塞进表格；长文本使用等宽滚动区域，保证审批信息可读且不挤压布局。
- 历史数据只显示“摘要型 diff”状态；只有重新生成候选并完成验证后，才允许获得完整 before/after 发布证据。

## Risks / Trade-offs

- [候选内容体积较大] → 保留摘要默认展示，完整内容按需展开，并限制 API 返回单次内容大小。
- [旧提案缺少 before 内容] → 显示明确不完整状态，禁止从当前版本反推历史内容。
- [文本 section 解析不稳定] → 对无法定位的 section 标记校验失败，不静默降级为可发布。
- [前后端字段迁移] → API 同时兼容旧摘要字段和新结构化字段，前端对旧数据显示迁移提示。

## Migration Plan

1. 扩展模型和提案生成逻辑，写入结构化变更明细与候选快照。
2. 为验证、批准和发布增加一致性校验；历史提案只读兼容。
3. 更新详情页，增加 section 级 before/after、最终候选内容和 materialization 目标。
4. 补充新旧数据、增删改 section、校验失败和长内容展示测试。
5. 若回滚本 change，保留旧 diff 字段读取，关闭新发布确认区即可，不影响既有版本指针。
