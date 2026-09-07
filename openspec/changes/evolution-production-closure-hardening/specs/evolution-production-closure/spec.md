## Purpose

这个能力用于把自进化从“能跑起来”推进到“能长期稳定运行”的生产闭环，重点覆盖基线锁定、冷却去重、发布边界、反馈回流和隔离约束五个控制面环节。

## ADDED Requirements

### Requirement: Proposal baseline must be fixed at creation time
系统 SHALL 在提案创建时冻结目标 artifact 的正式基线版本，并 SHALL 在验证、审批和发布阶段持续校验该基线未发生漂移。

#### Scenario: Proposal is created from a run
- **WHEN** 触发器生成新的提案
- **THEN** 系统 SHALL 记录该提案对应的正式基线版本，并 SHALL 在后续阶段以该版本作为唯一参考

#### Scenario: Baseline changes before verification
- **WHEN** 提案创建后、验证前正式基线版本发生变化
- **THEN** 系统 SHALL 阻止继续验证或发布，并 SHALL 要求重新生成提案或重新验证

### Requirement: Cooldown window must participate in trigger deduplication
系统 SHALL 将冷却窗口作为触发去重的一部分，并 SHALL 在冷却期内抑制重复触发、重复提案和重复验证。

#### Scenario: Same trigger fires repeatedly inside cooldown
- **WHEN** 同一目标 Artifact 在冷却窗口内再次触发
- **THEN** 系统 SHALL 视为重复触发并 SHALL 不创建新的候选提案

#### Scenario: Cooldown expires
- **WHEN** 冷却窗口已过且仍然存在新的失败信号
- **THEN** 系统 SHALL 允许重新进入提案生成流程

### Requirement: Release pipeline must preserve a hard promotion boundary
系统 SHALL 将 promote / rollback 视为受控发布边界，并 SHALL 在任一关键步骤失败时保持正式版本处于已知稳定状态。

#### Scenario: Publish step fails after version creation
- **WHEN** 发布过程中版本记录已创建但后续 materialization 或校验失败
- **THEN** 系统 SHALL 保持正式生效版本不前移，并 SHALL 记录补偿结果

#### Scenario: Rollback step fails
- **WHEN** 回滚目标可识别但实际回滚执行失败
- **THEN** 系统 SHALL 保持当前正式版本不变，并 SHALL 暴露明确的失败原因供人工介入

### Requirement: Post-release feedback must auto-route into the control loop
系统 SHALL 将发布后的观测、失败样本、回滚建议和高风险反馈自动路由到 Bad Case、stop 或 rollback 候选，而不是只在查询接口中展示。

#### Scenario: Observe endpoint returns rollback suggestion
- **WHEN** /post-release/observe 产生明确的回滚建议
- **THEN** 系统 SHALL 创建可追踪的后续动作候选或工单记录，并 SHALL 进入后续自动处理流程

#### Scenario: Repeated post-release failures accumulate
- **WHEN** 同一 artifact 在短时间内持续产生高风险反馈或失败样本
- **THEN** 系统 SHALL 能够自动提升处理等级，并 SHALL 触发 stop 或 rollback 候选

### Requirement: Overlay verification must enforce stronger runtime isolation
系统 SHALL 将 overlay 视为隔离验证层的一部分，并 SHALL 明确限制候选内容对正式运行时状态、文件系统和共享资源的影响范围。

#### Scenario: Candidate run uses overlay
- **WHEN** 候选提案进入验证运行
- **THEN** 系统 SHALL 仅允许候选内容在受控隔离范围内可见，并 SHALL 不污染正式运行时状态

#### Scenario: Runtime component exceeds overlay boundary
- **WHEN** 某个 runtime 组件需要访问未授权的正式资源
- **THEN** 系统 SHALL 阻断该访问并 SHALL 将其记录为隔离边界违规
