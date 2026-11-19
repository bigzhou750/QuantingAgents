## Purpose

为 Skill 提供显式的候选召回、TopK 重排、最终路由和降级能力，使“当前请求应该考虑哪些 Skill、最终加载哪个 Skill”成为可配置、可审计、可评测的系统行为，替代完全依赖 LLM 从全量摘要中隐式选择。

## ADDED Requirements

### Requirement: Skill routing index must be maintained

系统 MUST 维护可选的路由索引，包含 Skill 名称、描述、触发边界、负向规则、工具依赖、类别、版本、owner 和路由状态，并 MUST 支持策略版本快照。缺少路由元数据的 Skill MUST 从显式候选集中排除或以 `not_indexed` 标记，不得伪造触发边界。

#### Scenario: Index a routable skill
- **WHEN** 管理员为 Skill 补充路由元数据并启用路由
- **THEN** 系统将该 Skill 纳入可路由候选集并保存路由索引版本

#### Scenario: Missing routing metadata
- **WHEN** Skill 没有路由索引或索引版本过期
- **THEN** 系统将该 Skill 标记为不可路由并记录缺失原因

### Requirement: Router must produce a bounded candidate subset

显式路由层 MUST 接受任务输入，按配置策略执行候选召回和 TopK 重排，并 MUST 输出有序候选 Skill 列表、路由策略版本、候选来源、置信度和耗时。候选列表为空、策略异常或 TopK 配置无效时 MUST 返回显式失败状态。

#### Scenario: Route task to skill candidates
- **WHEN** 用户提交需要数据源查询能力的任务
- **THEN** 路由层返回包含相关数据源 Skill 的候选列表，并记录策略版本和召回依据

#### Scenario: No candidate matches
- **WHEN** 任务意图无法匹配任何已索引 Skill
- **THEN** 路由层返回空候选集和低置信原因，不强行选择一个 Skill

### Requirement: Main agent context must consume routed candidates

启用显式路由时，主 Agent 的系统 prompt MUST 只注入路由层输出的候选 Skill 摘要，而不注入全量 Skill 摘要；最终执行仍 MUST 通过 `load_skill` 加载正文。路由禁用时 MUST 保留现有全量摘要和 `load_skill` 行为。

#### Scenario: Context uses routed candidates
- **WHEN** 路由策略启用且返回 TopK 候选
- **THEN** 主 Agent 上下文只包含这些候选的 Skill 摘要

#### Scenario: Router disabled
- **WHEN** 路由策略关闭
- **THEN** Agent 继续使用现有全量 Skill 摘要方式选择 `load_skill`

### Requirement: Route decisions must be auditable

每次显式路由 MUST 生成 `skill_route` 事件，记录候选 Skill、最终选中、未选原因、策略版本、模型/召回器版本、耗时和 fallback 原因；缺失原因 MUST 标记为 `reason_unavailable`，不得编造路由依据。

#### Scenario: Audit a routed decision
- **WHEN** 路由完成后管理员查看审计链
- **THEN** 系统显示候选集、最终路由结果、策略版本和未选原因

#### Scenario: Router omits a reason
- **WHEN** 底层召回或重排未输出选择理由
- **THEN** 系统保存 `reason_unavailable` 并允许后续补全或人工复核

### Requirement: Router failure must degrade safely

路由模块异常或超时时 MUST 根据风险分级降级：低风险任务回退为现有全量摘要模式并标记路由失败；高风险任务 MUST 暂停后续自主 Skill 加载，保存原始 trace 并创建人工复核，不得静默忽略路由结果。

#### Scenario: Low-risk fallback
- **WHEN** 低风险任务路由超时
- **THEN** 系统回退到原 Skill 选择流程，并在 trace 中标记 `routing_failed`

#### Scenario: High-risk fail closed
- **WHEN** 高风险任务路由异常
- **THEN** 系统暂停 Skill 加载并创建人工复核任务

### Requirement: Routing metrics must be observable

系统 MUST 计算显式路由指标，至少包括候选召回率、准确率、误触发率、漏触发率、静默绕过率、路由延迟和路由成本，并 MUST 支持按策略版本、模型、Skill 和环境聚合。缺少 Ground Truth 或事件不完整时 MUST 标记为不可用，不写入伪造指标。

#### Scenario: Compute routing recall and precision
- **WHEN** 评测集包含正样本、负样本和边界样本
- **THEN** 系统按路由结果计算召回率、准确率和误触发率

#### Scenario: Silent bypass is measured
- **WHEN** 路由选中 Skill 但主 Agent 后续从未加载该 Skill
- **THEN** 系统将该样本标记为静默绕过并计入路由指标

### Requirement: Router strategy and deployment must be versioned

路由策略 MUST 支持创建不可变版本、启用/回滚和灰度切换，并 MUST 记录每次路由调用使用的策略版本。启用新策略前 MUST 能在独立路由评测集上对比新旧策略指标。

#### Scenario: Deploy new router strategy
- **WHEN** 管理员创建新路由策略版本并跑路由评测
- **THEN** 新版本与旧版本在同一数据集上形成可对比指标

#### Scenario: Rollback router strategy
- **WHEN** 新策略出现准确率回退或高风险失败
- **THEN** 系统允许回滚到旧策略版本并保留审计记录
