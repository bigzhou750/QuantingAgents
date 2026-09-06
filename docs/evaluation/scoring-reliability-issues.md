# 评测打分机制可靠性与准确性评审

> 评审日期：2026-09-06
>
> 评审范围：`app/services/eval`、`app/models/eval.py`、`app/routers/eval.py` 以及相关测试。

## 1. 结论

当前评测平台已经具备较好的工程治理骨架，但“打分结果”本身还不能称为可靠，也不能说“保证了打分准确性”。

可以依赖的能力：

- 规则类检查稳定、可复现。
- 评分来源、评分器版本、原因、原始输出和人工复核记录可追溯。
- 幻觉指标在数据模型上区分了人工真值与系统预测。
- 未安装、未启用、跳过的外部评分器不会被简单当成真实低分。

暂时不能依赖的能力：

- 将 `evidence_quality` 当成事实校验或幻觉检测准确率。
- 将 `llm_judge` 当成有证据支撑的事实性评审。
- 将 `pass@k` 直接理解为“质量通过率”。
- 将数据集版本号直接理解为“不可变可重放快照”。

当前评分更适合作为开发期的相对回归指标，不适合直接作为发布准确性门槛。

## 2. 可靠的部分

### 2.1 评分治理

- `ScoreStatus` 区分 `passed/failed/skipped/not_configured/error`，摘要和复核队列会过滤非真实评分。
- `EvalScore` 保存 `scorer_version`、`evidence_refs`、`claims`、`raw_output`。
- 人工复核保留 `original_score`，并追加 `review_audit_trail`。

### 2.2 幻觉指标的口径

`compute_hallucination_metrics` 明确要求 `truth_label` 和 `prediction_label` 都存在，未标注的 Claim 不会进入 Precision/Recall/F1 分母。

这是一个正确的治理口径：没有人工真值，就不应宣称检测准确率。

## 3. 幻觉检测的问题

### 3.1 证据评分不是事实校验

`EvidenceQualityScorer` 的实际实现是：

1. 按句号、感叹号、问号切分最终输出。
2. 对 Claim 和证据文本做中文 2/3-gram 与英文单词提取。
3. 计算重叠 token 数占 Claim token 数的比例。
4. 达到阈值就判为 `supported`。

参考实现：

- Claim 抽取：`app/services/eval/scorers/evidence_scorer.py:150`
- n-gram 判定：`app/services/eval/scorers/evidence_scorer.py:235`
- `supported` 阈值：`app/services/eval/scorers/evidence_scorer.py:252`

影响：

- 一个数字、实体或时间被改错的 Claim，只要和证据共享足够多的词汇，就可能被误判为有支撑。
- 例如证据写“营收 1500 亿”，输出写“营收 500 亿”，n-gram 重叠仍可能很高。
- 当前分数只能解释为“与检索文本的词汇相似度”，不能解释为“事实正确”。

### 3.2 矛盾型幻觉必然漏检

代码中没有任何分支会把 Claim 标记为 `contradicted`：

- 有足够重叠 -> `supported`
- 部分重叠 -> `weakly_supported`
- 没有匹配 -> `unsupported`

参考实现：`app/services/eval/scorers/evidence_scorer.py:252` 到 `app/services/eval/scorers/evidence_scorer.py:272`

但预测标签又包含 `contradicted`：

```python
claim.prediction_label = claim.verdict in (
    ClaimVerdict.UNSUPPORTED,
    ClaimVerdict.CONTRADICTED,
)
```

参考实现：`app/services/eval/scorers/evidence_scorer.py:275`

影响：当人工真值为 `contradicted` 时，系统几乎不可能预测为真，幻觉指标中的矛盾型 Recall 天然接近 0。

### 3.3 无法评估时仍给出高置信失败分

当最终输出为空且没有证据事件时，当前返回：

```python
score=0.0
passed=False
confidence=1.0
reason="无输出内容且无证据事件，无法评估证据质量"
```

参考实现：`app/services/eval/scorers/evidence_scorer.py:55`

Spec 要求“缺少必要证据时明确标记不可评分或低置信，而不是伪造分数”。当前实现虽然返回失败，但置信度是 1.0，仍可能被后续摘要和复核队列当成确定结论。

## 4. LLM Judge 的问题

### 4.1 Judge 没有接地

Judge prompt 只包含：

- 用户输入
- Agent 输出
- rubric 文本

参考实现：`app/services/eval/scorers/llm_judge_scorer.py:134`

没有传入：

- trace 中的检索证据
- 工具返回原文
- 参考答案 / `expected_output`
- 数据时间窗口

因此 rubric 中的 `factual_consistency` 无法真正做事实校验，只能让 LLM 凭文本感觉给分。

### 4.2 运行时的 Judge 配置没有生效

创建 run 时，`judge_model`、`rubric_version`、`low_confidence_threshold`、`review_strategy` 会写入 run snapshot：

`app/services/eval/runner_service.py:174`

但 `ScorerHub` 注册 LLM Judge 时使用默认构造：

```python
self.register_scorer(LLMJudgeScorer())
```

参考实现：`app/services/eval/scorer_hub.py:94`

`LLMJudgeScorer` 默认模型是 `qwen-plus`：

`app/services/eval/scorers/llm_judge_scorer.py:86`

影响：用户配置的 Judge 模型和 rubric 只用于展示快照，不实际控制本次评分。

### 4.3 依赖缺失时使用 mock 分数

当 `dashscope` 未安装时，`_call_judge` 会返回一个写死的 mock 结果：

```json
{"overall_score": 0.5, "overall_reason": "mock: dashscope SDK not installed"}
```

参考实现：`app/services/eval/scorers/llm_judge_scorer.py:203`

这个 mock 分数随后会以 `confidence=0.85` 保存为真实 LLM Judge 评分：

`app/services/eval/scorers/llm_judge_scorer.py:152`

影响：环境缺少依赖时，评测不是显示“未配置”，而是可能生成稳定的 0.5 分，污染整体评分。

## 5. 指标语义问题

### 5.1 expected_output 未被消费

全仓库搜索显示 `expected_output` 目前只被保存、展示和导入，没有 scorer 使用它作为评分依据。

Golden Case 中的 `expected_output.must_include` 也没有对应检查。

唯一接近的输出检查是 `expected_output_type`：

`app/services/eval/scorers/output_scorer.py:58`

影响：Case 的“参考答案”和“必须包含内容”对最终分数没有约束力。

### 5.2 pass@k 不是质量通过率

`compute_pass_at_k` 中“通过”定义为 trial 状态为 `completed`：

```python
passed = sum(1 for t in trials if t.get("status") == "completed")
```

参考实现：`app/services/eval/metrics_service.py:230`

影响：

- 输出内容错误但运行完成的 trial 也会被计为 pass。
- `pass@k` 和 `pass^k` 更适合命名为执行成功指标，不应直接作为质量门禁。

## 6. 可复现性问题

### 6.1 数据集更新会覆盖旧版本

`update_case` 使用原地 `update_one` 修改 case 文档，再递增数据集 patch 版本：

`app/services/eval/dataset_service.py:301`

旧版本的 case 内容没有被保存为不可变历史版本。

### 6.2 执行阶段没有使用 run snapshot

创建 run 时会把 case 内容写入 `RunSnapshot.case_contents`：

`app/services/eval/runner_service.py:147`

但真正执行时又从数据库重新拉取 case：

`app/services/eval/runner_service.py:251`

如果 run 创建后 case 被修改，同一 run 的后续执行或历史重放可能读到新内容，而不是创建时锁定的内容。

## 7. 人工真值的现状

幻觉分类指标依赖人工 `truth_label`，这是目前唯一能称为“准确性依据”的部分。

当前实现：

- 支持按 Claim 保存 `truth_label`、`hallucination_type`、`label_version`。
- 未标注 Claim 不会参与分类指标。
- 人工复核可以覆盖分数并保留原始分数。

当前不足：

- 没有多人标注一致性校验（例如 Cohen's Kappa）。
- Claim 标注只保存最新值，没有完整修改历史。
- 没有“证据引用”作为结构化标注字段，证据依据主要靠备注文字。
- 没有定期抽样验证人工标注本身是否稳定。

## 8. 修复优先级建议

### P0：先让分数不“伪装成准确”

1. 将无法评估的证据评分改为低置信或 `not_configured`，不要返回 `confidence=1.0`。
2. 删除 LLM Judge 的 mock 回退；依赖不可用时必须走 `not_configured`。
3. 将运行时的 `judge_model`、`rubric`、`rubric_version` 真正传入评分器。
4. 将 `pass@k` 改为基于真实评分通过，或者明确改名为执行成功率并禁止用于发布门禁。

### P1：补检测器自身的准确率验证

1. 建立一小批人工标注 Claim 作为校验集。
2. 在这些标注上计算 `evidence_quality` 的 Precision、Recall、F1。
3. 加入数字、实体、时间被篡改的对抗样本，确保不会被 n-gram 判成 `supported`。
4. 增加真正的矛盾检测，或在无法检测时不要把 `contradicted` 放进预测映射。

### P2：补可复现性和评分闭环

1. Case 更新时保存不可变版本，或执行时统一使用 run snapshot。
2. 为 `expected_output` / `must_include` 增加独立 scorer。
3. 将 LLM Judge 的 prompt 接入 trace 证据、参考答案和数据窗口。
4. 为 Claim 标注增加证据引用、标注历史和多人一致性校验。

## 9. 当前测试验证

已执行：

```bash
pytest -q tests/test_hallucination_metrics.py tests/test_eval_phase2.py tests/test_eval_phase3.py
```

结果：`66 passed`。

说明：现有测试主要验证模型结构、流程状态和 mock 行为，不验证“评分器对人工标注的准确率”，因此测试通过不代表打分准确。

## 10. 相关文件

- `app/services/eval/scorers/evidence_scorer.py`
- `app/services/eval/scorers/llm_judge_scorer.py`
- `app/services/eval/scorer_hub.py`
- `app/services/eval/metrics_service.py`
- `app/services/eval/runner_service.py`
- `app/services/eval/dataset_service.py`
- `app/models/eval.py`
- `app/routers/eval.py`
- `docs/evaluation/agent-evaluation-platform-usage-and-gaps.md`
