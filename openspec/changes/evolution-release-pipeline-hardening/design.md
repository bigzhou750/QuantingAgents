## Context

See proposal.md - Why. 当前实现已经有 artifact registry、proposal、verification、approval 和 promote 这条链路，但 Skill 的正式落盘仍然依赖本地用户目录，且 publish / rollback 的原子性和环境隔离并未被抽象成统一能力。

## Goals / Non-Goals

**Goals:**
- 让所有 artifact 类型共享统一的发布和回滚抽象
- 让 Skill 的生效位置不再绑定开发者本机 home 目录
- 保留版本历史、回执和审计轨迹，支持按环境切换当前版本

**Non-Goals:**
- 不重写提案生成或验证计算逻辑
- 不改变现有审批权限模型
- 不在本变更里重做前端大页面，只补足发布可见性

## Decisions

- 保留 MongoDB 中的 artifact registry / version 作为版本事实来源，因为系统已经在这里保存了内容快照和当前版本指针，适合继续承载版本治理。
- 引入类型感知的 materializer / publisher 抽象，而不是把 Skill、Prompt、Policy、Rubric、Case 分别做成完全不同的发布流程，因为共同的生命周期和门禁已经是同一套。
- 将本地文件系统目录降级为运行时 materialization cache，而不是权威数据源，因为生产环境需要可迁移、可回滚、可多实例复用。
- 将发布流程切分为“创建版本、materialize、发布后校验、切换当前指针、写回执”几个逻辑阶段，因为这比直接原地覆盖更容易做失败补偿和审计。
- 为不同环境显式维护当前版本指针，因为开发、测试和生产需要独立的发布节奏和回滚边界。

## Risks / Trade-offs

- [多存储一致性复杂] → 通过“先写版本、再 materialize、最后切指针”的顺序减少不一致窗口，并保留回滚补偿
- [本地目录迁移成本] → 通过把旧目录定位为 cache，并在迁移期保留兼容读取降低风险
- [类型抽象过宽导致实现变慢] → 用同一生命周期模型 + 类型适配器控制复杂度，不在每个 artifact 上重造一套流程

## Migration Plan

1. 把发布入口收敛到统一的 artifact publisher 接口。
2. 将 Skill 现有写盘流程迁移到可配置的 runtime root，并保留旧路径的兼容读取。
3. 为每次发布补充版本指针和回执写入，确保回滚可恢复。
4. 最后再把前端版本历史、发布结果和回滚记录接进后台页面。
