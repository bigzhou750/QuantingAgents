## Context

See proposal.md - Why. 当前自进化模块已经有 proposal、artifact registry、verification、approval、promote、rollback、receipt 和 trigger 服务，但它们之间主要通过约定字段连接，candidate overlay、状态前置条件、预算门禁和调度执行仍缺少统一的强制边界。

## Goals / Non-Goals

**Goals:**

- 建立唯一的 proposal 状态机和治理门禁服务，所有 API、后台任务和 runner 都复用同一套校验。
- 为 candidate verification 建立 per-run overlay context，使候选 artifact 真正进入 runtime，同时保持线上运行隔离。
- 让版本锁、幂等键、预算、allowlist、Release Gate、stop hook、smoke test 和通知审计可执行、可回放。
- 将线上反馈和发布版本关联起来，为发布后退化检测和 rollback 提供输入。

**Non-Goals:**

- 不允许自进化修改核心 Python 代码、评测评分口径、测试集或样本切分。
- 不在本 change 中实现新的 LLM 优化算法或完整知识图谱。
- 不把自动 promote 作为生产默认行为；生产默认继续要求人工审批。
- 不迁移历史 proposal/receipt 的业务含义，只增加兼容读取和补充治理字段。

## Decisions

### 1. 用共享 Governance Policy 作为唯一门禁

新增治理策略服务，统一执行状态转换、allowlist、change budget、版本锁、质量门槛、每日预算和 stop reason。路由层只负责认证和参数校验，服务层负责所有业务门禁，避免不同入口绕过检查。

替代方案是分别在 approval、promote、scheduler 中增加判断，短期改动小但容易产生状态不一致，因此不采用。

### 2. Candidate overlay 通过显式 run context 传递

verification 创建带签名/唯一 ID 的 overlay context，包含 proposal、artifact、基线版本、候选版本、sandbox 路径和允许的数据集版本。runner 创建 trial 时复制该 context，并由 runtime loader 按 context 读取候选内容。普通生产 run 没有 overlay context 时只能读取 active artifact。

overlay 使用临时目录和只读输入快照；清理失败会阻止 promote，不能只记录日志后继续发布。

### 3. Promote 使用乐观锁和原子状态变更

proposal 保存基线 artifact version、verification id 和 gate receipt。promote 前重新读取 registry 与 verification，确认版本未变化、验证成功、审批有效、门禁通过。写入新版本、更新 proposal 和 receipt 时使用 MongoDB 事务；不支持事务的环境使用幂等状态记录和补偿检查。

### 4. Scheduled trigger 使用统一调度入口

复用现有 APScheduler，在自进化启用且 cron 非空时注册一个调度 job。job 只负责读取 enabled policy、申请窗口锁并调用 `scheduled_check`；真正的 trigger/proposal 去重由治理服务负责。默认关闭和重复执行不应依赖前端状态。

### 5. 线上反馈采用关联表而不是复制大对象

线上样本、trace、Bad Case 和 release receipt 只保存引用 ID、摘要、版本和时间窗口，原始内容继续由已有集合保存。这样既能审计回放，也避免在多个集合复制敏感输出。

### 6. 兼容旧数据并逐步启用

历史 proposal 没有 baseline version、gate result 或 overlay context 时只允许查看和重新验证，不允许直接 promote。新字段使用可选读取和显式 `legacy_unverified` 标记。先在测试/实验环境开启 overlay 和 gate，完成 shadow 验证后再启用生产写回。

## Data Flow

```text
trigger/schedule/online feedback
          ↓
  dedupe + governance policy
          ↓
       proposal
          ↓
  baseline lock + candidate overlay
          ↓
   eval runner with overlay context
          ↓
 metrics + safety + grounding + gate
          ↓
 approval → promote → smoke test → receipt
          ↓
 online observation → stop/rollback suggestion
```

## Risks / Trade-offs

- [Risk] Overlay 与 runtime loader 不一致导致验证结果失真 → Mitigation：在 trial trace 中记录实际加载的 artifact/version，并增加 candidate-only marker 测试。
- [Risk] MongoDB 事务不可用或中途失败 → Mitigation：使用幂等操作键、状态机和补偿任务，promote 只允许单向进入中间状态。
- [Risk] 自动门禁误阻断正常候选 → Mitigation：保存每个 gate 的原始指标和失败原因，允许人工查看但不能无审计绕过。
- [Risk] 线上反馈包含敏感信息 → Mitigation：沿用 trace 脱敏、引用 ID 和最小化摘要，不在通知中发送原始 prompt/output。
- [Risk] 定时任务重复触发 → Mitigation：MongoDB 窗口锁、proposal 指纹和冷却时间三层去重。

## Migration Plan

1. 增加治理字段、状态机、policy、lock、overlay 和 receipt 扩展，旧数据标记为 `legacy_unverified`。
2. 先让 runner 以只读 shadow 模式加载 overlay，并验证正式运行不读取候选内容。
3. 接入状态机、allowlist、版本锁、Release Gate 和 stop hook，关闭绕过路径。
4. 接入 APScheduler 定时触发，默认保持关闭；补充手动触发和重复触发测试。
5. 开启测试环境 promote、smoke test、rollback 和通知；验证通过后再开放生产 promote。
6. 接入线上反馈关联和发布后退化检查。

回滚策略：先关闭 `EVOLUTION_ENABLED` 和调度 job；保留历史 candidate/receipt；如正式版本已发布，使用 artifact registry 的稳定版本 rollback，并运行 smoke test。不得通过删除 MongoDB 记录回滚治理状态。

## Test Strategy

- 模型和状态机：覆盖所有合法/非法状态转换、旧数据兼容和幂等键。
- Overlay：验证 candidate/production 读取边界、数据集隔离、异常清理和 trace context。
- Gate：覆盖 allowlist、版本冲突、预算、质量退化、安全退化和 stop reason。
- API：覆盖审批、promote、rollback、scheduler、线上样本和通知失败审计。
- 集成：使用 fake runtime + Mongo fixture 完成 trigger → proposal → verify → approve → promote → rollback 全链路。
- 前端：覆盖状态展示、门禁失败、版本冲突、回滚和定时任务默认关闭。
- 运行验证：在启用配置和关闭配置各启动一次服务，确认路由注册、权限和正式研究链路不回归。
