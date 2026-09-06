## Context

当前评测平台已经有评分器中心、Claim-Evidence 结构、人工复核和指标聚合，但评分器仍以启发式结果直接当作事实质量分，Judge 配置没有进入实际执行链路，数据集“版本”也不是不可变快照。详见 `proposal.md` 的 Why 和 `specs/agent-evaluation-platform/spec.md` 的契约变化。

## Goals / Non-Goals

**Goals:**

- 让证据评分明确区分“检索相关性”和“事实正确性”，并支持 `unscorable`。
- 让 Judge 的 model、rubric、rubric version 在 run 中真正生效，并把证据或参考答案传入 prompt。
- 让缺失依赖和无法评估的样本走 `not_configured` / `unscorable` / 低置信路径。
- 让 `pass@k` 基于质量评分通过，而不是仅基于执行完成。
- 让 run 执行和评分使用创建时锁定的 snapshot，支持历史重放。
- 让 `expected_output` 和 `must_include` 成为真实评分输入。
- 让 Claim 真值标注可审计，并支持多人标注一致性。

**Non-Goals:**

- 不重写 Vibe Agent runtime 或普通投资分析主流程。
- 不引入必须联网才能运行的评分依赖；LLM entailment 作为可选增强。
- 不做线上实时幻觉拦截，只改评测平台评分口径。
- 不承诺通过本 change 实现“绝对无幻觉”，只保证分数不再冒充事实准确率。

## Decisions

### 1. 扩展评分状态和 Claim 状态

`ScoreStatus` 增加 `unscorable` 和 `not_applicable`，保留 `passed/failed/skipped/not_configured/error`。`ClaimVerdict` 增加 `unscorable`。

理由：Spec 要求“缺少证据时明确不可评分”，现有状态只能表示跳过、未配置或错误，无法表达“有输出但证据不足以判定”。

替代方案：复用 `low confidence` 字段。不足：分数仍会进入真实评分聚合，无法阻止被误当成确定结论。

### 2. 证据评分拆成“检索相关性”和“事实支撑”两步

保留现有 n-gram 作为检索相关性信号，但不再由 n-gram 直接产生 `supported`：

1. Claim 抽取后先生成检索候选证据。
2. 对数字、股票代码、日期、实体等可机械化字段执行结构化一致性检查。
3. 语义型 Claim 可选接入 LLM entailment 检查。
4. 只有证据确实覆盖同一事实时才输出 `supported`；只有文本相似但事实未确认时输出 `weakly_supported` 或 `unscorable`。

每条 Claim 保存 `verification_method`，例如 `structured_numeric_check`、`entailment_judge`、`lexical_only`。

理由：金融幻觉主要集中在数字、实体和时间，结构化检查比 n-gram 可靠；LLM entailment 适合补充语义判断，但不能单独作为事实来源。

### 3. Judge 按 run 配置实例化

`ScorerHub.score_trial` 增加 run config 参数。LLM Judge 不再只注册全局默认实例，而是按当前 run 的 `judge_model`、`rubric`、`rubric_version` 创建评分实例；未显式配置时继续使用默认 rubric，但必须记录默认值。

Judge prompt 统一从 `JudgeContextBuilder` 生成，包含：

- 用户输入和最终输出
- trace 中可用的 evidence/retrieval/citation 片段
- `expected_output` 或 Case 评分标准
- 数据窗口
- rubric 与版本

理由：现有实现把配置写进 snapshot 却不传入 scorer，导致界面配置和实际评分脱节。

替代方案：让全局 judge 实例持有配置。不足：并发 run 可能使用不同 judge 配置，全局状态会被互相污染。

### 4. Judge 缺失时失败关闭

`LLMJudgeScorer` 增加显式 `is_available` 能力，SDK、模型或密钥不可用时由 `ScorerHub` 写入 `not_configured`。删除 mock 回退，禁止把 0.5 写死结果作为真实评分。

理由：当前 mock 回退会产生稳定但无意义的分数，比评分失败更危险。

### 5. 新增 ExpectedContentScorer

新增独立 scorer 消费：

- `expected_output.must_include`
- `scoring_criteria.required_fields`
- `scoring_criteria.required_sections`
- `scoring_criteria.forbidden_phrases`
- `scoring_criteria.required_tool_types`

Case 没有 `expected_output` 和对应标准时返回 `not_applicable`，不参与质量 pass。

理由：现有 golden case 的参考答案只保存不消费，导致 Case 设计者和评分结果脱节。

### 6. pass@k 拆成质量口径和执行口径

`compute_pass_at_k` 增加 `mode` 参数：

- `quality`：trial 只有同时满足执行完成、有效评分存在、所有要求 scorer 通过时才计为 pass。
- `execution`：保留现有执行完成口径，显式命名为执行成功率。

默认评测报告和 Release Gate 使用 `quality`；历史数据缺少完整评分时返回 `not_available`，不得用执行成功代替。

理由：Spec 要求 pass@k 默认基于质量评分；直接改现有指标会破坏历史比较，所以保留显式执行口径。

### 7. 数据集改为不可变版本 + run snapshot 执行

`eval_cases` 以 `(case_id, version)` 保存历史版本。更新和删除不再原地修改：

- 更新：插入新版本 case 文档，旧文档保留。
- 删除：写入 archived 状态，不物理删除历史。
- 列表查询：按目标版本选择每个 case 的最新可用版本。

`runner_service` 执行时直接使用 `run.snapshot.case_contents`，不再从 `eval_cases` 重新拉取当前内容。评分也使用 snapshot 中的 `scoring_criteria`。

理由：现有 run snapshot 已经存在但没有用于实际执行；只有 snapshot 成为唯一输入源，才能保证 run 创建后 case 被改也不影响历史重放。

### 8. Claim 标注独立历史

`ClaimEvidence` 增加 `annotation_history` 列表，每条标注包含：

- `annotation_id`
- `reviewer`
- `truth_label`
- `hallucination_type`
- `evidence_refs`
- `comment`
- `label_version`
- `timestamp`

现有 `truth_label` 保留为当前有效真值，便于旧接口兼容。幻觉指标在多人标注存在时，必须先按一致性策略聚合；没有达到一致性门槛时不得输出单值 Precision/Recall/F1。

理由：当前标注 API 只保存最新值，无法审计修改和多人分歧。

## Risks / Trade-offs

- [Risk] 结构化检查只覆盖可机械化字段，语义型幻觉仍可能漏检 → 语义型 Claim 使用可选 LLM entailment，并保留人工复核作为最终 gate。
- [Risk] LLM entailment 自身也可能幻觉或受 prompt 影响 → entailment 只输出 `supported/weakly_supported/unsupported/contradicted/unscorable` 候选，关键样本必须人工复核。
- [Risk] 修改 `pass@k` 口径会让历史 run 对比口径不一致 → 新旧接口分别返回质量口径和执行口径，并在报告中展示口径字段。
- [Risk] 不可变 case 版本会增加 Mongo 存储 → run 只保存创建时 snapshot，历史 case 可按需归档；不把全量历史复制到每次评分。
- [Risk] Judge prompt 加入证据和参考答案后上下文变大 → 使用结构化片段、截断和证据选择策略，并保留原始输出用于复核。
- [Risk] 新状态 `unscorable/not_applicable` 可能被旧前端误显示为低分 → 前端和聚合接口按新状态过滤，旧状态映射只作为兼容降级。

## Migration Plan

1. 数据模型先加可选字段，不迁移历史数据；旧记录缺少新字段时保持现有行为或返回 `not_available`。
2. 评分器先增加 `unscorable/not_applicable` 输出，聚合和复核队列同步识别。
3. Judge 配置生效后，先在小范围 run 对比默认配置和 run 指定配置的 raw output。
4. `pass@k` 先同时返回 `quality` 和 `execution` 口径，前端默认展示 quality。
5. case 版本化先新增写路径，历史 run 仍通过既有 snapshot 字段兼容；再切换 runner 使用 snapshot。
6. 回滚策略：所有新增字段和状态保持向后兼容；若新版指标异常，可切回旧 scorer 和旧 `pass@k` 实现，数据无需回滚。

## Open Questions

- 是否需要把语义 entailment 独立成可插拔 scorer，还是先作为 `evidence_quality` 的内部模块。当前设计倾向后者，避免新增外部依赖面。
