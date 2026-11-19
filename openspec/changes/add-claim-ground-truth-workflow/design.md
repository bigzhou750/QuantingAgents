## Context

当前幻觉分类指标已经具备 `ClaimEvidence`、`prediction_label`、`truth_label`、`annotation_history` 和 `compute_hallucination_metrics()`。缺口在于真值没有可复用的数据集来源，人工复核页也只展示 Claim 而不提供标注写入，LLM Judge 只输出连续质量分，未进入 Claim 级分类指标。See proposal.md for motivation.

## Goals / Non-Goals

**Goals:**
- 为离线评测集增加可复用的 `gold_claims` 真值结构，并随 run snapshot 固化。
- 提供批量真值导入、Claim 标注 UI 和覆盖率门禁，让 Precision/Recall/F1 的统计口径透明。
- 增加 Claim 级 LLM 幻觉预测，作为与规则型 Evidence Scorer 并列的独立预测来源。

**Non-Goals:**
- 不把 LLM 输出自动当作人工真值。
- 不改造非幻觉类的 LLM 连续质量分、Ragas 或 DeepEval 评分语义。
- 不重写 Claim 抽取流水线和现有 Evidence Scorer 的判定逻辑。
- 不自动生成“真实答案”，只提供人工预置真值和标注工作流。

## Decisions

### 1. 真值模型使用 `gold_claims + hallucination_seeds` 两层结构

`EvalCase.gold_claims` 保存人工预置的正确答案级真值；`hallucination_seeds` 保存“如果实际输出出现该断言，应视为幻觉”的负样本。两者都复用现有 `ClaimTruthLabel` 和 `HallucinationType` 枚举，避免引入新的标签体系。

理由：`gold_claims` 适合评估“应该说的内容”，`hallucination_seeds` 适合工具失败、错误数值、错误实体等易构造幻觉场景，可以降低全量人工打标成本。

替代方案：只在 `eval_scores.claims[].truth_label` 后置标注。能支撑单次指标，但不能复用为独立离线评测集，故不选。

### 2. run snapshot 直接固化 case 的真值字段

现有 `RunSnapshot.case_contents` 已经保存 case 内容，扩展时只需保证 `case_contents[case_id]` 包含 `gold_claims`、`hallucination_seeds` 和 `label_version`。评分与指标从 snapshot 读取，不直接读当前 EvalCase。

理由：复用现有 snapshot 机制，避免新增一套真值版本链。

### 3. 批量导入按 `score_id + claim_id` 幂等写入

新增批量标注导入，输入为 JSON/CSV，核心字段：

```text
score_id
claim_id
truth_label
hallucination_type
evidence_refs
label_version
comment
```

每条记录只更新真值相关字段和 `annotation_history`，不覆盖 `prediction_label`。重复提交同一条记录时，按 `score_id + claim_id + label_version` 覆盖并追加历史。

理由：与现有单个标注 API `POST /api/eval/scores/claims/annotation` 行为一致，同时支持 300+ 评测集的脚本化标注。

### 4. Claim 标注队列使用 `review_strategy` 和覆盖率门禁

`review_strategy` 语义确定为：

```text
auto    只把低置信度/低分 Claim 放入标注队列
all     要求所有 eligible Claim 完成标注后才输出真实指标
manual  人工选择数据集/范围做标注，指标标记为子集口径
```

指标聚合返回：

```text
labeled_claims
unlabeled_claims
eligible_claims
excluded_claims
label_coverage
review_strategy
```

只有 `label_coverage` 达到 `min_label_coverage` 且存在可计算分母时，才返回可用 Precision/Recall/F1。

理由：低置信度队列适合找问题，不适合直接代表全集指标；覆盖率字段把“全量指标”和“抽样子集指标”区分开。

### 5. LLM Claim Judge 作为独立 scorer 接入

新增 `claim_llm_judge` scorer，复用现有 `JudgeLLMClient` 和 judge 配置。它接收：

```text
最终输出
Claim 抽取结果
证据/trace 事件
工具结果
gold_claims / hallucination_seeds
```

输出每条 Claim 的：

```text
claim_id
verdict
prediction_label
prediction_reason
verification_method
```

结果保存为独立的 `eval_score`，`scorer_name=claim_llm_judge`，不影响 `evidence_quality` 的 Claims。幻觉指标支持按 `scorer_name + scorer_version` 分别聚合，不把连续质量分混入分类指标。

理由：规则型 Evidence Scorer 适合机械可判定事实，LLM Claim Judge 适合语义兜底，两者应独立曝光效果。

## Risks / Trade-offs

- [ground truth 预置成本高] → `hallucination_seeds` 覆盖工具失败、错误数值、错误实体等高价值负样本，`gold_claims` 只覆盖核心断言，不必穷举每条输出。
- [gold claims 与实际输出 Claim 文本不一致] → gold claims 先用于 LLM Judge 参考和种子匹配，不默认把所有实际输出自动对齐到 gold claims；自动对齐仅限归一化后可精确匹配的 Claim。
- [抽样标注导致指标有偏] → 指标返回 `review_strategy`、`label_coverage` 和 `not_available`，抽样结果只作为子集指标展示。
- [LLM Claim Judge 增加成本和延迟] → 仅离线评测/低置信度 re-verify 执行，不作为在线主链路必要评分器。
- [评分器版本导致指标不可比] → 指标聚合按 `scorer_name + scorer_version + label_version` 分组，历史指标不跨版本混算。

## Migration Plan

1. 先扩展 `EvalCase` 和 `ClaimEvidence` 可选字段，保持 Pydantic 模型向后兼容。
2. 在 dataset 导入和 run snapshot 生成时透传 `gold_claims` / `hallucination_seeds`。
3. 增加批量标注 API，并用脚本回填历史 `eval_scores.claims[].truth_label`。
4. 前端接入 Claim 标注表单和覆盖率展示。
5. 再接入 `claim_llm_judge` scorer；未配置时返回 `not_configured`，不影响旧 Run。

回滚策略：所有新增字段可选，关闭/移除新 scorer 后，旧评分链路和指标仍可运行。

## Open Questions

- 是否需要把抽样标注的置信区间落到指标 API，还是第一版只返回样本量和覆盖率。该问题不阻塞数据模型和 UI 主链路，可在指标展示阶段确定。
