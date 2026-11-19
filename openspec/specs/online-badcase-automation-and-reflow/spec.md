# online-badcase-automation-and-reflow Specification

## Purpose

提供线上 Agent 会话问题的自动发现、质量判定、去重、复核路由和评测样本回流能力，让线上 Bad Case 能以带证据、带版本、可复现的方式进入自进化闭环。

## Requirements

### Requirement: Online sessions must generate Bad Case candidates automatically
系统 MUST 在线上 Vibe Agent 会话进入终态时自动检查执行结果、trace、最终输出和用户反馈，并生成可追踪的 Bad Case 候选。

#### Scenario: Runtime failure generates candidate
- **WHEN** 线上任务返回 `attempt.failed`、超时、异常中断或空输出
- **THEN** 系统 MUST 自动创建带有来源 session、task、trace、失败原因和 artifact 版本的 Bad Case 候选

#### Scenario: Completed output is evaluated
- **WHEN** 线上任务成功完成并产出最终结果
- **THEN** 系统 MUST 使用配置的规则、轨迹、证据、安全和 Judge 信号对该输出进行评估，并保存评估来源与版本

#### Scenario: Online evaluation must not block production
- **WHEN** 自动判定失败、评分器不可用或采样任务后台执行异常
- **THEN** 系统 MUST 不阻断原有会话、SSE、任务中心和最终输出，并记录失败日志

### Requirement: Bad Case must record failure family and detection signals
系统 MUST 为每个自动创建的 Bad Case 候选保存失败家族、检测信号列表、置信度和判定依据，使后续复核和自进化可以解释该样本为何被判为失败。

#### Scenario: Structured detection signal is stored
- **WHEN** 自动判定将一个线上样本标记为 Bad Case
- **THEN** 系统 MUST 保存 `failure_family`、`detection_signals[]`、`detection_confidence`、`severity`、`reason`、`detector_name` 和 `detector_version`

#### Scenario: Each signal keeps evidence references
- **WHEN** 检测信号来自工具事件、evidence 事件、评分结果或用户反馈
- **THEN** 系统 MUST 在对应信号中保存可查询的 trace、score、trial 或 session 引用

#### Scenario: Detector version changes do not rewrite history
- **WHEN** 某个评分器或判定规则升级
- **THEN** 系统 MUST 保留历史样本判定时的信号版本，不得用新版本静默覆盖历史判定

### Requirement: Automatic routing must separate confirmed, review, and ignored samples
系统 MUST 按失败家族、置信度和严重级别将候选路由到直入池、人工复核队列或仅指标记录，且不得仅凭单次低质量分数直接进入正式评测集。

#### Scenario: Hard execution failure routes directly
- **WHEN** 候选属于超时、空输出、runtime 失败或确定权限违规
- **THEN** 系统 MUST 自动将候选写入 Bad Case 池，并标记为可进入 Online Regression Set

#### Scenario: Single low judge score routes to review
- **WHEN** 唯一信号是单次 LLM Judge 低分，且没有规则、证据或用户反馈佐证
- **THEN** 系统 MUST 将该候选放入人工复核队列，不得自动进入 Bad Case 池

#### Scenario: Safety risk requires confirmation
- **WHEN** 候选包含安全或合规风险标签
- **THEN** 系统 MUST 自动创建 Bad Case 并设置 `review_required=true`，在人工确认前不得进入 Golden Set

#### Scenario: Occasional low quality is only recorded
- **WHEN** 候选低质量但置信度低于阈值、严重级别为低且无用户反馈
- **THEN** 系统 MUST 仅记录统计指标或低频采样，不得产生重复 Bad Case

### Requirement: Bad Case creation must deduplicate repeated failures
系统 MUST 使用输入、失败家族、失败特征、artifact 版本和数据窗口生成去重指纹，避免同一线上问题反复创建重复 Bad Case 或评测 Case。

#### Scenario: Repeat failure merges into existing case
- **WHEN** 同一用户或不同用户再次触发相同失败模式
- **THEN** 系统 MUST 更新已有 Bad Case 的出现次数、最近时间、受影响版本和会话数量，而不是新建记录

#### Scenario: Different failure family creates separate case
- **WHEN** 相同输入分别产生证据不足和工具失败
- **THEN** 系统 MUST 为不同失败家族创建不同 Bad Case

#### Scenario: Data window affects dedup boundary
- **WHEN** 相同输入在不同数据窗口或 artifact 版本下失败
- **THEN** 系统 MUST 将两者视为独立样本，因为失败可能由外部数据或版本变化引起

### Requirement: User feedback must be captured and linked
系统 MUST 在自然语言研究工作台提供用户反馈能力，并将反馈内容、会话、任务和输出版本关联到 Bad Case 候选。

#### Scenario: User marks answer as wrong
- **WHEN** 用户对某条 Agent 回答标记“回答错误”
- **THEN** 系统 MUST 保存反馈类型、session、task、最终输出和当前 artifact 版本，并创建复核候选

#### Scenario: User provides free-form feedback
- **WHEN** 用户提交文字反馈
- **THEN** 系统 MUST 保存原文，并允许复核人判断是事实错误、内容无用、风险披露不足还是其他类型

#### Scenario: Feedback is anonymous or missing session
- **WHEN** 反馈缺少合法 session/task 上下文
- **THEN** 系统 MUST 拒绝创建不可追踪的 Bad Case，或仅保存脱敏后的独立反馈记录

### Requirement: Bad Case reflow must preserve correct sample semantics
系统 MUST 按失败家族将 Bad Case 转为回归 Case、负向 Case、标签样本或人工修订样本，并禁止把原始坏输出直接作为 `expected_output`。

#### Scenario: Execution failure reflows as regression case
- **WHEN** Bad Case 属于执行失败或工具失败
- **THEN** 系统 MUST 创建以输入和失败约束为主的评测样本，不设置坏输出为期望输出

#### Scenario: Evidence or hallucination reflows as labeled sample
- **WHEN** Bad Case 属于证据不足、矛盾或幻觉问题
- **THEN** 系统 MUST 保存 truth label、幻觉类型或失败规则，并让评分标准验证该失败模式不再出现

#### Scenario: Safety reflow is gated
- **WHEN** Bad Case 属于安全合规问题
- **THEN** 系统 MUST 在人工确认和标签录入完成后才允许回流到正式评测集

#### Scenario: User feedback requires curated answer
- **WHEN** 用户反馈指出正确回答但系统没有可靠参考答案
- **THEN** 系统 MUST 将样本保留为负向或复核样本，不得自动生成虚假的期望输出

### Requirement: Reflowed cases must retain provenance and version context
系统 MUST 在每一次 Bad Case 回流时保存来源 Bad Case、trace 引用、数据窗口、artifact 版本、发布回执和创建时间，并生成新的数据集 patch 版本。

#### Scenario: Reflow creates immutable dataset version
- **WHEN** Bad Case 被加入某个数据集
- **THEN** 系统 MUST 创建或推进该数据集版本，并把 `reflow_from_bad_case_id`、来源上下文和检测信号写入元数据

#### Scenario: Financial context is explicit
- **WHEN** 回流样本依赖行情、新闻或财报数据
- **THEN** 系统 MUST 保存数据时间窗口；无法保存快照时，MUST 标记样本为不可完整回放

#### Scenario: Replay is not guaranteed
- **WHEN** 线上 trace 被删除、会话已归档或数据快照不存在
- **THEN** 系统 MUST 仍允许样本进入复核或结构回归，但 MUST 明确标记不可完整回放

### Requirement: Evaluation datasets must separate sample maturity
系统 MUST 将自动回流样本、复核样本、检测器样本和人工确认样本分层管理，避免低质量或未确认样本污染 Golden Set。

#### Scenario: Online regression set accepts hard failures
- **WHEN** 高置信执行失败或工具失败被自动确认
- **THEN** 系统 MUST 允许其进入 Online Regression Set，并保留自动判定来源

#### Scenario: Review queue holds uncertain samples
- **WHEN** 样本只有单一 Judge 低分、模糊反馈或低置信证据信号
- **THEN** 系统 MUST 将其放入 Review Queue，不进入 Online Regression 或 Golden Set

#### Scenario: Detector set is separate from agent behavior set
- **WHEN** 样本需要验证幻觉或安全检测器本身的准确率
- **THEN** 系统 MUST 将其放入 Detector Evaluation Set，并与 Agent 行为回归集隔离

#### Scenario: Golden set requires human confirmation
- **WHEN** 自动样本需要进入 Golden Set
- **THEN** 系统 MUST 要求人工确认、标签版本和期望行为明确后才能进入

### Requirement: Bad Case events must feed evolution trigger
系统 MUST 在 Bad Case 入池、去重合并或高风险事件发生后通知自进化触发器，并遵守现有阈值、冷却窗口和权限约束。

#### Scenario: Threshold triggers proposal check
- **WHEN** 未处理 Bad Case 数量达到配置阈值
- **THEN** 系统 MUST 按现有 trigger 机制触发检查，并允许生成候选人提案，但 MUST NOT 直接修改生产 artifact

#### Scenario: High-risk event triggers review escalation
- **WHEN** Bad Case 的严重级别为 high 或 critical
- **THEN** 系统 MUST 记录升级事件，并允许进入人工复核或候选修复流程

#### Scenario: Evolution is disabled
- **WHEN** 自进化功能未启用或冷却窗口生效
- **THEN** 系统 MUST 继续收集 Bad Case，并记录触发被抑制的原因

### Requirement: Existing manual workflow must remain compatible
系统 MUST 保持现有 Bad Case 手工 API、页面和转换接口兼容，并允许旧数据缺少新增字段时正常读取。

#### Scenario: Manual online sample still works
- **WHEN** 管理员继续通过后台或 `/api/eval/online-sample` 手动提交样本
- **THEN** 系统 MUST 支持原有输入结构，并可将新字段作为可选扩展

#### Scenario: Legacy Bad Case records are readable
- **WHEN** 历史 Bad Case 缺少 `failure_family`、`detection_signals` 或 `dedup_key`
- **THEN** 系统 MUST 正常展示并允许复核，不得因新增模型字段导致反序列化失败

### Requirement: Online Bad Case collection must protect sensitive data
系统 MUST 对自动采集的内容执行脱敏、大小限制和访问控制，并避免将未清洗的敏感数据直接写入共享评测集或外部系统。

#### Scenario: Credentials are redacted
- **WHEN** 输入、输出或 trace 中包含 API key、token、密码、身份证、手机号或银行卡号
- **THEN** 系统 MUST 在保存 Bad Case 或回流样本前执行脱敏

#### Scenario: Large content is bounded
- **WHEN** 输入、输出或 trace 超过配置大小限制
- **THEN** 系统 MUST 保存摘要、哈希或外存引用，不无限扩大 Bad Case 文档

#### Scenario: Access is restricted to internal roles
- **WHEN** 非管理员或测试用户访问自动采集的 Bad Case 和评测样本
- **THEN** 系统 MUST 拒绝访问，并沿用现有评测平台权限边界
