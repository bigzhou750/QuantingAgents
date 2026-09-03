## Purpose

为自进化闭环提供可审计、可阻断、可回滚的生产治理能力，确保候选 artifact 在隔离环境中真实验证，并且任何正式发布都经过版本、质量、安全、预算和人工门禁检查。

## ADDED Requirements

### Requirement: Candidate artifacts must be executed in an isolated overlay

系统 MUST 为 candidate verification 创建隔离 overlay，并让该 verification run 的 Agent、Skill、Prompt、Policy、Rubric 和 Case 读取候选版本；线上正式运行 MUST 不读取 candidate 或 sandbox 内容。

#### Scenario: Candidate overlay is used by verification

- **WHEN** 管理员启动一个有效 proposal 的 verification run
- **THEN** runner MUST 携带不可伪造的 overlay context 执行任务，并在 trace 和 verification record 中记录 candidate artifact、基线版本和 overlay 位置

#### Scenario: Overlay is isolated from production

- **WHEN** candidate verification 正在运行
- **THEN** 候选文件、配置和数据覆盖 MUST 只对该 verification run 可见，不得修改正式 artifact、正式配置或其他用户的线上运行

#### Scenario: Overlay cleanup fails

- **WHEN** verification 完成、失败、取消或超时后 sandbox 清理失败
- **THEN** 系统 MUST 标记 cleanup failure、阻止 promote，并保留清理失败路径和审计记录

### Requirement: Proposal lifecycle must enforce verification and approval ordering

系统 MUST 强制 proposal 只能按受控状态机流转，未完成验证、验证失败、门禁失败或未获得有效人工审批的 proposal MUST 不得 promote。

#### Scenario: Approve an unverified proposal

- **WHEN** proposal 尚未有通过的 verification record
- **THEN** approve 操作 MUST 被拒绝，并返回当前状态和缺失的验证条件

#### Scenario: Promote a verified proposal

- **WHEN** proposal verification 通过、Release Gate 通过、基线版本未变化且人工审批有效
- **THEN** 系统 MUST 原子地创建正式 artifact 新版本、更新 proposal 状态并写入 receipt

#### Scenario: Promote with stale baseline

- **WHEN** proposal 基于的 artifact 版本已经不是 registry 当前版本
- **THEN** promote MUST 被拒绝并要求重新验证，不得覆盖较新的正式版本

#### Scenario: Invalid state transition

- **WHEN** 请求跳过 verifying、verified 或 approved 状态
- **THEN** 系统 MUST 拒绝状态变更并保留原状态

### Requirement: Governance gates must be enforced before promotion

系统 MUST 在验证和发布前执行 allowlist、change budget、每日预算、质量门槛、安全门槛、回归检查和人工门禁；任何失败 MUST 触发 stop policy 或阻止后续阶段。

#### Scenario: Artifact is outside the allowlist

- **WHEN** proposal 的 artifact、路径、类型或修改 section 不符合 registry allowlist
- **THEN** proposal MUST 被拒绝或标记为 forbidden，且不得进入 verification 或 promote

#### Scenario: Verification budget is exceeded

- **WHEN** 当日 verification run 数量或成本超过配置预算
- **THEN** 系统 MUST 停止新 verification，记录 `budget_exceeded` stop reason，并通知管理员

#### Scenario: Candidate introduces a regression

- **WHEN** candidate 在固定验证集或 holdout 集的成功率、安全评分、grounding、延迟或成本不满足 gate
- **THEN** 系统 MUST 阻止 promote，保存差异和失败样本，并记录 gate failure

#### Scenario: Safety degradation is detected

- **WHEN** candidate 的安全评分低于基线或出现新的高风险标签
- **THEN** 系统 MUST 停止闭环并要求人工复核，不得自动发布

### Requirement: Scheduled evolution checks must be actually scheduled and idempotent

系统 MUST 支持由配置 cron 驱动的定时自进化检查，默认关闭；同一时间窗口、同一失败模式和同一 artifact MUST 不重复创建 proposal。

#### Scenario: Scheduled check is disabled

- **WHEN** schedule 配置为空或自进化功能关闭
- **THEN** 调度器 MUST 不执行自进化检查，并且不得创建 proposal

#### Scenario: Scheduled check fires

- **WHEN** schedule 已启用且达到 cron 时间
- **THEN** 系统 MUST 检查趋势回退、Bad Case 阈值和失败聚类，记录调度结果，并按规则创建或复用 proposal

#### Scenario: Duplicate trigger occurs

- **WHEN** 相同 run、失败模式和 artifact 已有待处理 proposal
- **THEN** 系统 MUST 返回已有 proposal，不得创建重复 proposal

### Requirement: Promote and rollback must be consistent and recoverable

系统 MUST 让 MongoDB artifact 版本、磁盘 Skill、runtime cache 和 receipt 保持一致；rollback MUST 支持幂等执行并在恢复后运行 smoke test。

#### Scenario: Promote a Skill artifact

- **WHEN** Skill proposal 通过 promote
- **THEN** 系统 MUST 写入正式 Skill、更新 active version、失效旧 runtime cache，并保存 promote receipt

#### Scenario: Rollback a promoted artifact

- **WHEN** 管理员指定一个稳定版本执行 rollback
- **THEN** 系统 MUST 恢复该版本的存储和运行时可见内容，运行 smoke test，并保存 rollback receipt

#### Scenario: Rollback target is unavailable

- **WHEN** 指定版本不存在或内容校验失败
- **THEN** rollback MUST 被拒绝，不得改变当前 active version

### Requirement: Online feedback must be linked back to released versions

系统 MUST 将线上 run、trace、用户反馈、Bad Case、proposal、verification、released artifact version 和发布后质量指标建立可查询关联。

#### Scenario: Online failure becomes a bad case

- **WHEN** 线上样本被标记为失败、高风险或用户反馈失败
- **THEN** 系统 MUST 保存来源 run/version/trace，并允许将样本回流为带来源的 Bad Case

#### Scenario: Post-promote degradation

- **WHEN** 发布后质量、安全或成本指标达到回退阈值
- **THEN** 系统 MUST 关联到对应 release receipt，触发 stop 或 rollback 建议，并通知管理员

### Requirement: Production governance actions must be auditable and observable

系统 MUST 对 trigger、proposal、verification、gate、approval、promote、rollback、stop、smoke test 和通知保存 actor、时间、request/run id、基线版本、候选版本和结果。

#### Scenario: Inspect a governance receipt

- **WHEN** 管理员打开一条生产治理 receipt
- **THEN** 页面和 API MUST 展示完整状态链、版本差异、验证指标、门禁结果、审批记录、失败原因和后续动作

#### Scenario: Notification delivery fails

- **WHEN** 外部通知发送失败
- **THEN** 系统 MUST 保留通知失败记录和重试状态，但不得把治理动作误报为已通知
