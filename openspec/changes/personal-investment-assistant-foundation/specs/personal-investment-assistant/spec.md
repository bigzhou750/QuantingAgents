## Purpose

本能力用于把项目从通用股票研究平台推进为面向新手的个人投资助手。系统 SHALL 结合用户画像、持仓约束和策略偏好，生成可解释的研究、筛选与策略体检结果，而不是只输出泛化结论。

## ADDED Requirements

### Requirement: User can maintain an investment profile
系统 MUST 提供个人投资画像的维护能力，至少包括风险偏好、交易风格、资金区间、禁投规则、目标市场、持仓信息和默认上下文偏好。画像内容 MUST 可被保存、读取和更新，并且 MUST 与当前登录用户绑定。

#### Scenario: Create or update a profile
- **WHEN** 用户保存新的投资画像或修改已有画像
- **THEN** 系统 SHALL 持久化最新内容，并在后续研究任务中可被读取

#### Scenario: Invalid profile data
- **WHEN** 用户提交缺失关键字段或格式非法的数据
- **THEN** 系统 SHALL 拒绝保存，并返回可理解的校验错误

### Requirement: User can manage reusable strategy definitions
系统 MUST 提供策略管理能力，允许用户创建、编辑、停用和查看策略定义。每个策略 MUST 包含名称、适用市场、筛选条件、参数和说明。

#### Scenario: Create a strategy
- **WHEN** 用户保存一个新策略
- **THEN** 系统 SHALL 将其作为独立策略记录保存，并可在后续任务中复用

#### Scenario: Disable a strategy
- **WHEN** 用户停用某个策略
- **THEN** 系统 SHALL 在默认可选列表中隐藏该策略，但仍保留历史记录

### Requirement: Strategy screening MUST produce candidate pools, not buy instructions
系统 MUST 支持基于所选策略发起选股任务，并输出候选股票池、命中规则、主要风险与数据时间。结果 MUST 使用“候选 / 观察 / 风险提示”表述，MUST NOT 直接输出买入、卖出或目标价指令。

#### Scenario: Run a strategy screening task
- **WHEN** 用户选择一个策略并发起筛选任务
- **THEN** 系统 SHALL 返回符合规则的候选标的列表及每只标的的命中原因

#### Scenario: Strategy conflicts with profile constraints
- **WHEN** 候选标的与用户画像中的禁投规则或仓位约束冲突
- **THEN** 系统 SHALL 标记冲突原因，并降低该标的的展示优先级

### Requirement: Strategy fitness checks MUST be lightweight and explainable
系统 MUST 提供策略体检能力，用于判断某策略在当前市场环境下的适配度。体检结果 MUST 包含适配度结论、关键依据、风险提示和数据时间，且 MUST NOT 声称保证收益。

#### Scenario: Evaluate current market fit
- **WHEN** 用户对某个策略执行体检
- **THEN** 系统 SHALL 返回适配度结论和关键统计摘要，并说明其依据

#### Scenario: Data quality is insufficient
- **WHEN** 支撑体检的数据缺失、过期或不足以形成结论
- **THEN** 系统 SHALL 明确标记结果为不充分，并提示用户不要据此做结论

### Requirement: VibeAgent MUST receive controlled personal context
系统 MUST 在自然语言研究任务中注入受控的个人上下文摘要。该摘要 MUST 从投资画像、当前策略和持仓信息生成，并且 MUST 避免把原始敏感信息或未经归一化的自由文本直接拼入研究输入。

#### Scenario: Submit a research request with context
- **WHEN** 用户在研究工作台发起任务并选择带入个人画像
- **THEN** 系统 SHALL 将归一化后的上下文摘要与用户问题一起送入研究链路

#### Scenario: User disables context injection
- **WHEN** 用户关闭画像注入
- **THEN** 系统 SHALL 只使用当前问题和显式参数，不附带个人画像内容

### Requirement: Strategy results MUST be auditable
系统 MUST 记录策略筛选和策略体检任务的输入、输出、时间、数据来源和结果状态，以便复盘和排错。结果记录 MUST 能区分正常完成、失败和数据不足。

#### Scenario: Persist completed task result
- **WHEN** 策略筛选或体检任务完成
- **THEN** 系统 SHALL 保存任务输入、结果摘要和状态供用户后续查看

#### Scenario: Persist failed task result
- **WHEN** 任务因数据源失败、校验失败或执行异常而终止
- **THEN** 系统 SHALL 保存失败原因并向用户展示可读错误
