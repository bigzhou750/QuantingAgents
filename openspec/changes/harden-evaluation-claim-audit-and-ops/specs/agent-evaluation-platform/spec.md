## ADDED Requirements

### Requirement: Claim extraction must normalize input and preserve complete facts
评测系统 MUST 在 Claim 抽取前统一 CRLF、Unicode 空白和连续空白，MUST 对金额、百分号、日期、股票代码、括号和英文缩写等高风险片段进行跨行合并或保留为待确认候选，并 MUST 保留清洗前后的文本位置或映射关系。

#### Scenario: Cross-line stock code and EPS
- **WHEN** Agent 输出包含 `600519\nSH` 或 `EPS` 被换行拆开的事实片段
- **THEN** 系统 MUST 生成包含完整 `600519 SH` 或完整 `EPS` 的 Claim 候选，且 Claim 文本可回查原文位置

#### Scenario: Ambiguous numeric split
- **WHEN** 系统无法确定 `65\n66 元` 应合并为 `65.66 元` 还是其他数值
- **THEN** 系统 MUST 保留原始片段并降低其 Claim 候选优先级，MUST NOT 擅自拼成错误数值

### Requirement: Claim extraction must filter Markdown structure and format fragments
评测系统 MUST 识别 Markdown 标题、表格表头与分隔线、引用块、代码块、水平分隔线和只含字段名/格式标记的列表项，并将这些内容排除出 Claim 列表；包含完整事实的普通列表项 MUST 在去除列表标记后继续作为 Claim 候选。

#### Scenario: Header and field label are excluded
- **WHEN** 输出包含 `### 基本面分析` 和 `- **盈利能力**：`
- **THEN** 两者 MUST NOT 进入 Claim 评分分母，且系统 MUST 记录 `excluded_reason`

#### Scenario: Complete list item becomes a claim
- **WHEN** 输出包含 `- 2025 年净利润为 823 亿元。`
- **THEN** 系统 MUST 保留为 `2025 年净利润为 823 亿元。` 的 Claim 候选

### Requirement: Claim extraction must apply quantity limit after cleaning and report truncation
评测系统 MUST 在候选清理、过滤和排序之后应用单 trial 默认最多 20 条 Claim 的限制，MUST 返回 `claim_candidate_count`、`claim_count`、`claim_truncated`、`claim_truncated_count` 和 `claim_truncated_at`，并 MUST 记录被排除和被截断内容的原因或统计信息。

#### Scenario: Long report has leading format fragments
- **WHEN** 长报告前 20 个原始分割片段包含标题、目录和字段名，后续存在真实财务 Claim
- **THEN** 系统 MUST 先清理格式片段再应用数量上限，后续事实 Claim 不得因前 20 条被污染而被静默丢弃

#### Scenario: Claim count exceeds twenty
- **WHEN** 清理后的事实 Claim 超过 20 条
- **THEN** 系统 MUST 只输出前 20 条，并返回截断统计和截断位置，且截断内容不影响现有 `ClaimEvidence`、`ScoreResult.claims` 和 Claim-Evidence 映射接口

### Requirement: Excluded claims must not enter metric denominators
评测系统 MUST 将标题、纯格式行、字段标签、无法判断的残缺片段和被截断 Claim 排除出 `evidence_coverage`、`unsupported_ratio`、`weakly_supported_ratio` 和幻觉指标分母；指标返回 MUST 同时给出排除原因或统计，不能静默丢失。

#### Scenario: Metric denominators exclude filtered fragments
- **WHEN** 某个 trial 的候选片段包含标题和残缺数字，其余 Claim 有证据判定
- **THEN** 指标分母 MUST 只统计有效 Claim，并返回被排除数量和原因

### Requirement: LLM Judge must resolve model and provider from unified configuration
评测系统 MUST NOT 在 `LLMJudgeScorer`、`ScorerHub` 或 runner 中分别硬编码 `qwen-plus` 作为默认 Judge 模型；默认模型 MUST 来自唯一配置源，MUST 支持按 adapter 使用 DeepSeek、Qwen 或 OpenAI-compatible 等统一 LLM 通道，并 MUST 在 `run_config.judge_model` 提交时校验模型是否受支持。

#### Scenario: Unified default model is used
- **WHEN** 运行未显式指定 `judge_model`，且系统已配置受支持的默认 Judge 模型
- **THEN** 评分使用统一默认模型执行，并在 `raw_output` 中记录实际模型、adapter 和调用耗时

#### Scenario: Run requests unsupported judge model
- **WHEN** API 提交的 `run_config.judge_model` 不在受支持模型集合内
- **THEN** 服务端 MUST 返回明确 4xx 错误，而不是静默 fallback 到其他模型

### Requirement: LLM Judge unavailability must fail closed with observable reason
Judge 可用性 MUST 基于受支持的 adapter、对应凭据和模型集合判断；任何依赖不可用时评分 MUST 进入 `NOT_CONFIGURED` 或低置信路径，MUST NOT 使用 mock 分数或静默使用旧默认模型，并 MUST 在结果中记录失败原因。

#### Scenario: No judge credentials are configured
- **WHEN** 当前 adapter 缺少凭据或模型不在支持集合内
- **THEN** `LLMJudgeScorer.is_available` MUST 返回不可用，评分结果 MUST 返回 `NOT_CONFIGURED` 并记录明确原因

#### Scenario: Judge call fails during scoring
- **WHEN** 实际调用超时、鉴权失败或模型返回错误
- **THEN** system MUST 保留失败状态和可运维的失败原因，不得生成普通分数

### Requirement: Run snapshot must preserve case identity and validate before execution
评测运行创建时 MUST 将 `case_id` 写入 snapshot case value，而不只依赖字典 key；执行器消费前 MUST 校验每个 Case 存在稳定 `case_id`；历史快照缺少 value 中的 `case_id` 但 key 可补回时 MUST 自动兼容，两者都缺失时 MUST 抛出结构化 `CaseSnapshotValidationError`。

#### Scenario: Create run from real dataset
- **WHEN** 从标准 dataset case 调用 `create_run()` 并持久化 snapshot
- **THEN** snapshot 中每个 case value MUST 包含 `case_id`，且 `_resolve_run_cases()` 返回的 Case 可直接被执行器消费

#### Scenario: Historical snapshot has case_id only in key
- **WHEN** 旧 snapshot 的 case value 缺少 `case_id` 但字典 key 可用
- **THEN** 系统 MUST 从 key 补回 `case_id`，并保持运行可执行

#### Scenario: Snapshot cannot recover case_id
- **WHEN** case value 和字典 key 都无法提供 `case_id`
- **THEN** 系统 MUST 返回 `run_initialization_error`，不得在执行阶段抛出裸 `KeyError`

### Requirement: Run initialization failures must have structured failure stage and UI presentation
评测运行 MUST 在创建 Trial 前执行 run preflight，并 MUST 保存结构化的 `failure_stage`、`error_code` 和 `error_message`；运行初始化失败时 MUST 保持 `completed_trials=0`、`failed_trials=0`、`trial_count=0`，不得把“未创建 Trial”显示成 Trial 失败。

#### Scenario: Run initialization fails
- **WHEN** preflight 发现 snapshot 缺失 `case_id`、Case 数量不一致或 scorer/judge 配置不可用
- **THEN** 系统 MUST 将 Run 标记为 `failed`，保存结构化失败阶段和错误代码，并停止创建 Trial

#### Scenario: Run detail shows initialization failure
- **WHEN** 管理员打开初始化失败的 Run 详情
- **THEN** 页面 MUST 在状态摘要首屏展示运行状态、失败阶段、错误代码、错误原因和 Trial 未创建，而不是只显示 `0/63 完成，0 失败`
