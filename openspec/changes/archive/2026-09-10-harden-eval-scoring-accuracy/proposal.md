## Why

当前评测评分已经具备治理骨架，但评分结果本身还不够可靠：`evidence_quality` 使用 n-gram 相似度冒充事实支撑，`llm_judge` 未真正接入运行时配置和证据，`pass@k` 统计的是执行完成而不是评分通过，数据集版本也不是不可变快照。若继续把这些分数用于回归对比和发布门禁，会得到“看起来可量化、实际不可验证”的结论。

## What Changes

- 调整 `evidence_quality`：不再把 n-gram 重叠率高直接解释为事实正确；缺少必要证据或输出结构时 MUST 返回低置信/不可评分，而不是生成确定分数。
- 补齐矛盾检测能力，或在检测器尚不支持 `contradicted` 时不得生成矛盾幻觉预测；证据评分结果 MUST 区分 `supported`、`weakly_supported`、`unsupported`、`contradicted` 和 `unscorable`。
- 让 `judge_model`、`rubric`、`rubric_version` 在评测运行时真正生效；LLM Judge 的 prompt MUST 包含 trace 证据、工具返回或参考答案，不能只让模型凭文本感觉评分。
- Judge 依赖不可用时 MUST 进入 `not_configured`/低置信路径，不得回退到 mock 0.5 分并写入真实评分。
- 新增基于 `expected_output` 和 `must_include` 的内容覆盖评分，使 Golden Case 的参考答案真正影响结果。
- 修正 `pass@k` / `pass^k` 语义：默认基于质量评分通过，或者明确按执行成功率命名，并禁止两者混用。
- 将数据集版本改为不可变历史版本；run 执行和评分 MUST 使用创建时锁定的 snapshot，而不是后续重新读取可变 case。
- 扩展 Claim 人工真值：保存结构化证据引用、标注修改历史和多人一致性校验结果，幻觉指标才能作为检测器准确率的依据。
- 保持普通投资分析主流程不变；评测 API 和后台页面以向后兼容方式扩展字段和状态。

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `agent-evaluation-platform`: 在现有评测平台上增加评分可验证性、证据不足处理、Judge 配置落地、指标语义、不可变快照和 Claim 标注质量控制要求。

## Impact

- Backend：修改 `app/services/eval/scorers/evidence_scorer.py`、`app/services/eval/scorers/llm_judge_scorer.py`、`app/services/eval/scorer_hub.py`、`app/services/eval/metrics_service.py`、`app/services/eval/runner_service.py`、`app/services/eval/dataset_service.py`、`app/models/eval.py` 和相关评测 API。
- Data：MongoDB 中 `eval_cases`、`eval_runs`、`eval_trials`、`eval_scores` 需要支持不可变版本快照、unscorable 状态、Judge 配置链路和 Claim 标注历史；旧数据按缺失字段兼容。
- API/UI：`pass@k`、评分摘要、复核队列和 run 报告的口径会调整；评测后台展示新增不可评分、Judge 未配置和快照版本信息，普通研究工作台不受影响。
- Config：继续兼容现有 `EVAL_PLATFORM_ENABLED` / `VITE_EVAL_PLATFORM_ENABLED`；Judge 配置仍使用现有字段，但必须真正传递给 scorer。
- Tests：补充 n-gram 对抗样本、矛盾检测、Judge 配置生效、依赖缺失、`expected_output` 消费、snapshot 回放和 `pass@k` 语义测试。

验收标准：上述行为都有可运行测试覆盖；缺失证据和缺失 Judge 依赖的样本不会产生看似可信的确定分数；同一 run 在 case 更新后仍可通过 snapshot 重放出一致输入和评分标准。
