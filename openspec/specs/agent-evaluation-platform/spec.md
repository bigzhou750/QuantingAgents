# agent-evaluation-platform Specification

## Purpose

为 QuantingAgents 提供一个面向 Vibe Agent runtime 的生产级测评与治理能力，支持研发和管理员对 Agent 的答案质量、工具过程、证据链、安全边界、运行成本和版本回归进行持续验证。

## Requirements

### Requirement: Evaluation platform must manage versioned datasets and cases
系统 MUST 提供评测集、评测用例和版本管理能力，并且 MUST 以不可变历史版本保存 case 内容。运行创建时 MUST 固化 case 输入、参考答案和评分标准；运行执行与评分 MUST 使用该快照，而不是后续被修改或删除的 case 文档。

#### Scenario: Create versioned dataset
- **WHEN** 研发或管理员创建评测集并录入多个评测用例
- **THEN** 系统保存数据集版本、case 内容、标签、参考答案和评分标准，并可按版本查询

#### Scenario: Replay a dataset version
- **WHEN** 用户选择某个数据集版本发起评测运行
- **THEN** 系统 MUST 对该版本下的全部 case 使用相同输入和评分标准进行重放

#### Scenario: Case is updated after run creation
- **WHEN** 评测运行创建后，某个 case 的内容被修改
- **THEN** 已创建运行 MUST 继续使用创建时锁定的 case 内容执行和评分，并返回该运行使用的快照版本

#### Scenario: Case is deleted after run creation
- **WHEN** 评测运行创建后，某个 case 被删除
- **THEN** 已创建运行 MUST 仍可从 run snapshot 读取原输入和评分标准，不得因当前 case 文档缺失而丢失执行输入

### Requirement: Evaluation platform must execute repeated trials for each case
系统 MUST 支持每个 case 进行一次或多次 trial 运行，并记录每次运行的独立结果。

#### Scenario: Run multiple trials
- **WHEN** 用户为同一 case 指定多次 trial
- **THEN** 系统 MUST 保存每次 trial 的输入、输出、状态、耗时、token、错误和最终判定

#### Scenario: Trial failure is preserved
- **WHEN** 某个 trial 超时、取消、失败或返回空结果
- **THEN** 系统 MUST 保留失败原因和相关 trace，且不得覆盖其他 trial 的结果

### Requirement: Evaluation platform must preserve standardized trace and replayability
系统 MUST 将 Vibe Agent runtime 的消息、LLM 调用、tool、skill、Swarm、证据、错误和最终结果保存为可回放的标准化 trace。

#### Scenario: Record structured trace
- **WHEN** Agent 执行研究任务
- **THEN** 系统 MUST 记录与该 trial 关联的结构化事件序列，并支持按事件游标查看

#### Scenario: Recover after interruption
- **WHEN** 页面刷新或服务重启后重新查看同一 trial
- **THEN** 系统 MUST 通过持久化 trace 恢复显示历史过程，而不是依赖浏览器内存

### Requirement: Evaluation platform must provide layered scoring
系统 MUST 提供分层评分能力，至少包括 outcome、trajectory、金融质量、证据质量、工具过程、安全治理和运行成本。证据质量评分 MUST 区分“有证据支撑”“弱支撑”“无支撑”“矛盾”和“不可评估”；缺少必要证据、trace 或输出结构时 MUST 明确标记不可评分或低置信，MUST NOT 生成看似可信的确定分数。

#### Scenario: Score a completed trial
- **WHEN** trial 完成后进入评分阶段
- **THEN** 系统 MUST 为该 trial 生成多维分数和可读原因说明

#### Scenario: Score unavailable due to missing evidence
- **WHEN** 某一评分维度缺少必要证据、trace 或输出结构
- **THEN** 系统 MUST 将该维度标记为不可评分或低置信，且不得保存为高置信的通过/失败结论

#### Scenario: Evidence score uses only lexical overlap
- **WHEN** 输出 Claim 与证据文本有较高 n-gram 重叠，但关键数字、实体或时间与证据不一致
- **THEN** 系统 MUST NOT 仅凭词汇重叠将该 Claim 判为事实正确；结果 MUST 保留矛盾、无支撑或不可评估状态及判定依据

### Requirement: Evidence scoring must separate lexical similarity from factual support
系统 MUST 将 n-gram 或关键词相似度作为“检索相关性”证据，而不是“事实正确性”证据。每条 Claim 的判定 MUST 保存检测方法、证据引用、置信度和原因；当系统只能证明文本相似、无法证明事实一致时，MUST 使用 `weakly_supported`、`unsupported` 或 `unscorable`，不得生成 `supported` 结论。

#### Scenario: Contradictory numeric claim shares n-grams
- **WHEN** Agent 输出中的数字与证据中对应数字矛盾，但两者共享大量中文词汇
- **THEN** 证据评分 MUST NOT 将该 Claim 标记为事实 `supported`，且结果 MUST 保留矛盾或不可评估信息

#### Scenario: No evidence event exists
- **WHEN** Claim 没有任何可引用的 evidence/retrieval/citation 事件
- **THEN** 系统 MUST 将 Claim 标记为无支撑或不可评估，并返回低置信，不得声称有证据支撑

### Requirement: Contradiction predictions must be truthful
系统 MUST 只在真正执行冲突检测并发现冲突证据时生成 `contradicted` 预测；在检测器无法判断冲突时 MUST NOT 将 `unsupported` 或空状态映射成矛盾幻觉预测。

#### Scenario: Conflicting evidence is detected
- **WHEN** 两个证据片段或证据与输出存在可判定的冲突
- **THEN** 系统 MUST 生成 `contradicted` 判定，并保存冲突证据引用和判定原因

#### Scenario: Contradiction detector is unavailable
- **WHEN** 当前评分器没有实现矛盾检测，但人工真值为 `contradicted`
- **THEN** 系统 MUST 将该 Claim 的预测标记为不可用或漏检，不得伪造 `contradicted` 预测，也不得把它当成已检测成功

### Requirement: Expected output must influence scoring
系统 MUST 消费 Case 的 `expected_output` 和 `scoring_criteria` 中定义的必含内容、必含字段、禁止内容和输出结构约束；没有 `expected_output` 的 Case 必须明确标记该维度不适用，而不是把它当成无要求通过或固定低分。

#### Scenario: Required content is present
- **WHEN** Agent 输出覆盖 `expected_output.must_include` 中全部必含项
- **THEN** 输出覆盖维度 MUST 标记通过并展示逐项命中结果

#### Scenario: Required content is missing
- **WHEN** Agent 输出缺少任一 `expected_output.must_include` 项
- **THEN** 输出覆盖维度 MUST 标记失败，并列出缺失项，不得仅凭输出长度或字段存在性给分

#### Scenario: Case has no expected output
- **WHEN** Case 没有定义 `expected_output` 或相应评分标准
- **THEN** 输出覆盖维度 MUST 标记为 `not_applicable` 或 `skipped`，且不得参与质量 pass 统计

### Requirement: Claim truth annotation must be auditable and consistent
系统 MUST 为 Claim 人工真值保存结构化证据引用、标注来源、标签版本和修改历史；缺少标注来源或标签版本的 Claim MUST NOT 参与幻觉分类指标。多人标注存在时，系统 MUST 保留每次标注记录，并在指标中展示是否达到一致性门槛。

#### Scenario: Save a labeled claim
- **WHEN** 评测人员为 Claim 提交真值标签
- **THEN** 系统 MUST 保存结构化证据引用、标注来源、标签版本、修改时间和修改历史

#### Scenario: Missing annotation metadata
- **WHEN** Claim 存在真值标签，但缺少标注来源或标签版本
- **THEN** 系统 MUST 排除该 Claim 的幻觉分类指标，并返回缺失元数据的原因

#### Scenario: Multiple annotations disagree
- **WHEN** 同一 Claim 存在多个人工标注且结果不一致
- **THEN** 系统 MUST 保留全部标注记录，并在指标结果中展示标注数量、不一致状态或一致性结果，不得静默使用其中一条标注

### Requirement: Evaluation platform must support deterministic, judge-based, and human review scoring
系统 MUST 支持规则评分、LLM-as-judge 评分和人工复核，并 MUST 将评分来源、版本和覆盖关系持久化。LLM Judge 评分 MUST 使用运行创建时指定的 judge model、rubric 和 rubric version；Judge 输入 MUST 包含可用的证据或参考答案，不能仅凭 Agent 输出做事实性判断。Judge 依赖不可用或调用失败时 MUST 进入 `not_configured` 或低置信路径，MUST NOT 使用 mock 输出作为真实分数。

#### Scenario: Deterministic score check
- **WHEN** 评测需要检查 schema、权限、token、耗时、工具调用或格式约束
- **THEN** 系统 MUST 使用可重复的确定性规则给出结果

#### Scenario: Judge-based open-ended scoring
- **WHEN** 评测需要判断答案完整性、金融推理、证据相关性或风险披露
- **THEN** 系统 MUST 使用运行指定的固定版本 LLM-as-judge，将证据、参考答案和 rubric 传入 prompt，并保存 judge model、rubric 和原始输出

#### Scenario: Judge dependency is unavailable
- **WHEN** Judge SDK、模型或密钥不可用，或 Judge 调用失败
- **THEN** 系统 MUST 将对应评分标记为 `not_configured`/`error`/低置信，不得写入由 mock 或默认回退生成的普通分数

#### Scenario: Human review overrides score
- **WHEN** 管理员对低置信、高风险或边界样本进行人工复核
- **THEN** 系统 MUST 记录人工覆盖结果、复核人和原因，并保留原始评分

### Requirement: Evaluation platform must compute stability and regression metrics
系统 MUST 提供 pass@k、pass^k、方差、成功率、失败率、成本、延迟和 token 使用等稳定性和回归指标。`pass@k` 和 `pass^k` 默认 MUST 基于质量评分通过计算；执行完成但未达到评分门槛的 trial MUST NOT 计入质量 pass。若指标按执行成功计算，MUST 使用不同名称或明确标注口径。

#### Scenario: Compute stability metrics
- **WHEN** 同一 case 运行多个 trial
- **THEN** 系统 MUST 汇总这些 trial 的质量通过、执行成功、方差、延迟和成本，并标明各指标口径

#### Scenario: Trial completes but fails scoring
- **WHEN** trial 状态为 `completed`，但一个或多个有效评分低于通过阈值
- **THEN** 质量型 `pass@k` / `pass^k` MUST NOT 将该 trial 计为通过，并且指标结果 MUST 说明该样本已完成但未通过

#### Scenario: Compare two versions
- **WHEN** 用户选择两个不同 Agent 配置或版本
- **THEN** 系统 MUST 显示各维度指标差异、失败样本差异，以及两版指标的计分口径是否一致

### Requirement: Evaluation platform must support bad case feedback loop
系统 MUST 支持将线上失败、人工复核失败、安全拦截和用户反馈样本回流为新的评测用例或 bad case。

#### Scenario: Convert a failure into a bad case
- **WHEN** 某个 trial 经过复核被判定为失败或高风险
- **THEN** 系统 MUST 允许将其转存为可版本化的 bad case 并附带标签

#### Scenario: Reuse a bad case in regression
- **WHEN** 研发将 bad case 加入回归集
- **THEN** 系统 MUST 在后续运行中保留其历史来源和标签

### Requirement: Evaluation platform must preserve skill route and execution trace events

评测平台 MUST 在标准化 trace 中保存 `skill_route` 和 `skill_execute` 事件，并支持按 trial、run、Skill name 和 Skill version 查询。事件必须包含候选 Skill、选中 Skill、未选原因、加载结果、执行步骤和关联 tool call；缺失信息时 MUST 保留真实缺失标记。

#### Scenario: Record skill route decision
- **WHEN** Agent 在任务执行过程中调用 `load_skill` 或收到 Skill 路由结果
- **THEN** 系统保存包括候选 Skill、最终选择、选择理由或缺失原因的 `skill_route` 事件

#### Scenario: Record skill execution
- **WHEN** Skill 正文被加载并用于后续任务执行
- **THEN** 系统保存 `skill_execute` 事件，并可通过事件关联后续工具调用和最终输出

#### Scenario: Legacy trace has no skill event
- **WHEN** 旧 trial 中没有 `skill_route` 或 `skill_execute` 事件
- **THEN** 系统继续保留原 trace，并将 Skill 相关展示标记为不可用

### Requirement: Evaluation platform must support skill eval run variants and snapshots

评测运行 MUST 支持 Skill 评测变体配置，包括 `no_target_skill`、`skill_only` 和 `full_skill_set`，并 MUST 将目标 Skill、排除 Skill、Skill 集合快照、Skill 版本和运行时根目录写入 run snapshot。

#### Scenario: Create skill eval run
- **WHEN** 用户创建带 `skill_eval` 配置的评测运行
- **THEN** 运行快照保存 Skill 目标、变体、断言配置和相关版本信息

#### Scenario: Run snapshot keeps variants reproducible
- **WHEN** 后续按同一 run snapshot 重放
- **THEN** 系统使用相同 Skill 集合、变量配置和断言版本执行

### Requirement: Evaluation trial details must expose skill evaluation results

评测 trial 详情 MUST 展示 Skill 路由命中、执行断言、共存结果、无目标 Skill 基线对比和回归状态；新能力未启用或数据缺失时 MUST 显示显式不可用状态，不报错。

#### Scenario: Admin views skill eval trial
- **WHEN** 管理员打开包含 Skill 评测结果的 trial
- **THEN** 页面展示 route 结果、执行断言逐项结果和失败定位

#### Scenario: Skill eval not configured
- **WHEN** case 未配置 `skill_eval` 或运行未启用 Skill 评测
- **THEN** trial 详情对 Skill 区域显示 `not_configured`，其余评测内容保持正常

### Requirement: Evaluation platform must expose an internal management UI
系统 MUST 提供仅供研发和管理员使用的后台页面，用于管理评测集、发起运行、查看指标、回放 trace、复核分数和查看 bad case。

#### Scenario: Access evaluation UI
- **WHEN** 认证用户不具备研发或管理员权限
- **THEN** 系统 MUST 拒绝访问评测后台页面和相关 API

#### Scenario: View trial details
- **WHEN** 研发或管理员打开某个 trial
- **THEN** 页面 MUST 显示输入、输出、trace、分数、失败原因和复核状态

### Requirement: Evaluation platform must preserve existing product workflows
系统 MUST 不改变现有单股分析、批量分析、任务中心和自然语言研究工作台的既有行为契约。

#### Scenario: Existing analysis stays unchanged
- **WHEN** 用户提交现有单股分析或批量分析任务
- **THEN** 请求 MUST 继续进入原有链路，不经过评测平台

#### Scenario: Evaluation failures are isolated
- **WHEN** 评测平台或评测任务失败
- **THEN** 现有研究工作台和分析流程 MUST 仍可独立运行
