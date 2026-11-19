## Purpose

为 Agent 运行过程提供生产级结构化决策链、分层业务解释、解释一致性校验、统一审计追溯、生产观测和故障降级能力，使高风险业务能够回答“为什么选择、依据是什么、解释是否可信、由谁复核”。

## ADDED Requirements

### Requirement: Agent must emit structured decision records

Agent 运行系统 MUST 在每个关键决策节点生成结构化 `DecisionRecord`，至少包含决策场景、候选选项、选择依据、最终结论、关联证据 ID、父决策 ID、决策状态、置信度、模型或策略版本、产生时间和 trace 事件 ID；决策记录 MUST 能按任务或业务维度串联成完整决策链。

#### Scenario: Record a tool selection decision
- **WHEN** Agent 从多个可用工具中选择一个工具执行
- **THEN** 系统 MUST 保存包含候选工具列表、选中工具、选择依据、关联上下文和最终结论的结构化决策记录

#### Scenario: Record a long-chain task decision
- **WHEN** Agent 在多节点长链路任务中产生多个决策
- **THEN** 系统 MUST 使用父决策 ID 和顺序号串联这些节点，并支持按任务查询完整决策链

#### Scenario: Decision record lacks evidence
- **WHEN** 某个决策节点没有可关联的证据或上下文
- **THEN** 系统 MUST 保存该节点的决策状态为 `unverified` 并记录缺失原因，不得伪造证据关联

### Requirement: Tool calls must expose candidate options and selection rationale

系统 MUST 在工具调用 trace 中同时记录候选工具、最终选中工具和选择理由；当运行时无法提供候选或理由时 MUST 标记为 `candidates_unavailable` 或 `reason_unavailable`，不能只记录最终调用结果。

#### Scenario: Tool selected from registered tools
- **WHEN** Agent 在工具注册表范围内选择一个工具
- **THEN** 系统 MUST 保存候选工具标识、选中工具标识、选择理由和关联决策节点

#### Scenario: Runtime omits selection reason
- **WHEN** 底层模型或工具调用链没有输出选择理由
- **THEN** 系统 MUST 记录选择理由缺失，并允许后续结构化提取或人工复核补全，而不是静默生成解释

### Requirement: Layered explanations must match audience

系统 MUST 基于决策记录和证据生成至少三种解释：面向开发者的完整技术细节、面向业务人员的精简逻辑说明、面向终端用户的自然语言理由；各层解释 MUST 不直接暴露原始模型思考过程，并 MUST 标注解释生成版本和来源。

#### Scenario: Generate user-facing explanation
- **WHEN** 终端用户查看一次 Agent 研究结果
- **THEN** 系统 MUST 返回自然语言理由和可读的证据来源，不展示原始推理流

#### Scenario: Generate developer-facing explanation
- **WHEN** 开发者或管理员查看同一决策链
- **THEN** 系统 MUST 展示决策节点、候选比较、trace 事件、证据引用、模型版本和校验结果

### Requirement: Explanation consistency must be validated

系统 MUST 对生成的解释执行一致性校验，比较解释、决策记录、证据和最终输出；校验结果 MUST 至少包含 `consistent`、`inconsistent` 或 `unverifiable` 状态、原因、置信度和校验器版本；不一致解释 MUST 进入待复核状态。

#### Scenario: Explanation matches decision chain
- **WHEN** 解释与决策记录、证据和最终输出一致
- **THEN** 系统 MUST 将解释标记为 `consistent` 并允许在面向用户的界面展示

#### Scenario: Explanation contradicts decision chain
- **WHEN** 解释声称的依据与决策记录或证据不一致
- **THEN** 系统 MUST 将解释标记为 `inconsistent`，降低展示优先级，并生成人工复核任务

#### Scenario: Explanation cannot be verified
- **WHEN** 缺少决策记录、证据或校验所需版本信息
- **THEN** 系统 MUST 将解释标记为 `unverifiable`，并明确展示缺失内容

### Requirement: Unified audit chain must be queryable by business ID

系统 MUST 提供统一审计查询接口，允许按 `business_id`、`task_id` 或 `session_id` 拉取同一业务对象的完整决策链、标准化 trace、证据、最终输出、操作日志引用、解释校验结果和人工复核记录；接口 MUST 遵守用户隔离和权限控制。

#### Scenario: Audit by task ID
- **WHEN** 有权限的用户使用任务 ID 查询审计链
- **THEN** 系统 MUST 返回该任务从输入到最终输出的决策节点、trace 事件、证据、解释和复核状态

#### Scenario: Unauthorized audit query
- **WHEN** 用户尝试查询不属于自己的审计链且不具备管理权限
- **THEN** 系统 MUST 拒绝查询并记录审计日志

#### Scenario: Legacy data has no decision chain
- **WHEN** 业务对象创建于新决策链能力上线之前
- **THEN** 系统 MUST 返回已有 trace 或日志，并将决策链部分标记为 `legacy_unverified`

### Requirement: Production explainability metrics must be observable

系统 MUST 计算并暴露生产 Agent 决策链指标，至少包括决策链完整率、解释一致性、证据覆盖率、审计查询延迟和高风险暂停次数；指标 MUST 支持按时间、任务类型、模型、策略和风险等级聚合，并 MUST 在指标退化时触发告警。

#### Scenario: Compute decision chain completeness
- **WHEN** 一个生产任务完成
- **THEN** 系统 MUST 记录决策节点数、缺失决策节点数、证据关联比例和完整率

#### Scenario: Alert on consistency regression
- **WHEN** 解释不一致率或决策链完整率连续超过配置阈值
- **THEN** 系统 MUST 触发告警，并在审计工作台展示受影响的业务 ID

### Requirement: Explainability failure must trigger safe degradation

当决策记录、解释生成或校验模块发生故障时，系统 MUST 保留原始 trace 和操作日志；对高风险自主决策 MUST 暂停执行并转入人工复核；对低风险任务 MUST 继续执行但在输出中明确标记解释不可用和边界说明。

#### Scenario: Explanation module fails on high-risk task
- **WHEN** 高风险任务运行中解释生成或校验模块不可用
- **THEN** 系统 MUST 停止高风险自主决策，保存全量原始事件，并创建人工复核任务

#### Scenario: Explanation module fails on low-risk task
- **WHEN** 低风险任务运行中解释模块不可用
- **THEN** 系统 MUST 保留任务结果和原始 trace，并在输出中标记解释缺失，不阻断已有正常流程

### Requirement: High-risk decisions must have manual review fallback

系统 MUST 为高风险、解释不一致或不可验证的决策提供人工复核队列，并 MUST 记录复核人、动作、原因、原始结果和复核时间；未完成复核前，受影响的高风险决策 MUST 不作为可执行结果对外使用。

#### Scenario: Inconsistent explanation enters review queue
- **WHEN** 解释校验结果为 `inconsistent` 且决策风险等级为高
- **THEN** 系统 MUST 创建人工复核记录，并禁止将该决策作为无限制的可执行输出

#### Scenario: Reviewer completes audit
- **WHEN** 复核人提交通过、拒绝、调整解释或调整结论
- **THEN** 系统 MUST 保存完整复核审计轨迹并更新决策链状态
