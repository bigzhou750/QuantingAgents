## 1. 数据模型与 Run Snapshot

- [ ] 1.1 在 `app/models/eval.py` 新增 `GoldClaim` 和 `HallucinationSeed` 模型，复用 `ClaimTruthLabel` 与 `HallucinationType`，验证 Pydantic 序列化和枚举校验测试通过
- [ ] 1.2 为 `EvalCase` 增加可选 `gold_claims`、`hallucination_seeds` 和 `ground_truth_version` 字段，验证历史 Case 反序列化兼容
- [ ] 1.3 扩展 `ClaimEvidence` 或等价结构，保证批量真值写入可保留 `truth_source`、`label_version`、`annotation_history`，验证 `tests/test_hallucination_metrics.py` 中现有字段语义不回归
- [ ] 1.4 修改 `app/services/eval/runner_service.py` 创建 snapshot 时固化 case 的 `gold_claims`、`hallucination_seeds` 和 `ground_truth_version`，验证 snapshot 包含真值且创建后修改 Case 不影响 Run
- [ ] 1.5 修改 `app/services/eval/dataset_service.py` 的 add/update/import 流程透传真值字段，验证内置 golden case 导入后仍可读取新字段

## 2. 批量真值导入与标注 API

- [ ] 2.1 新增批量真值导入服务，按 `score_id + claim_id + label_version` 幂等写入 `eval_scores.claims`，验证返回成功/跳过/失败明细
- [ ] 2.2 新增 `POST /api/eval/scores/claims/batch-annotation`，支持 JSON 数组，验证权限、非法 label、缺失目标和不覆盖 `prediction_label` 的测试通过
- [ ] 2.3 新增数据集级 `gold_claims` 导入接口，验证重复导入按 `case_id + claim_text + label_version` 幂等更新
- [ ] 2.4 保留现有单条 `POST /api/eval/scores/claims/annotation` 兼容性，验证新旧接口写入同一 Claim 时不丢历史
- [ ] 2.5 为批量导入增加 CSV 解析与字段校验，验证错误行有明确原因且不会中断整体导入

## 3. Review Strategy 与指标覆盖率

- [ ] 3.1 在 `EvalRunConfig` 增加可选 `min_label_coverage`，验证默认值、0/1 边界和非法值校验
- [ ] 3.2 让 `review_strategy` 影响 Claim 标注队列：`auto` 低置信度/低分优先，`all` 全量，`manual` 抽样或人工指定范围，验证队列筛选结果符合策略
- [ ] 3.3 扩展 `app/services/eval/metrics_service.py`，返回 `labeled_claims`、`unlabeled_claims`、`eligible_claims`、`excluded_claims`、`label_coverage` 和 `review_strategy`
- [ ] 3.4 在 `compute_hallucination_metrics()` 增加覆盖率门禁，未达到 `min_label_coverage` 时 Precision/Recall/F1 返回 `not_available`
- [ ] 3.5 在 `/api/eval/runs/{run_id}/metrics` 返回覆盖率字段，验证部分标注和全量标注两种状态

## 4. 前端 Claim 打标与覆盖展示

- [ ] 4.1 扩展 `frontend/src/views/Evaluation/HumanReview.vue`，为每条 Claim 增加 `truth_label`、`hallucination_type`、`evidence_refs` 和 `label_version` 表单，验证提交后调用标注接口
- [ ] 4.2 在人工复核页显示当前 `review_strategy` 和 Claim 队列来源，验证 `auto/manual/all` 文案与状态正确
- [ ] 4.3 在 `frontend/src/views/Evaluation/RunDetail.vue` 展示标注覆盖率、未标注 Claim 数和指标 `not_available` 原因，验证空状态和已标注状态
- [ ] 4.4 在 `frontend/src/views/Evaluation/DatasetDetail.vue` 增加 `gold_claims` 导入/预览入口，验证导入返回汇总且不破坏既有 Case 编辑
- [ ] 4.5 运行 `vue-tsc --noEmit` 和相关前端组件测试，验证类型与交互无回归

## 5. Claim 级 LLM Judge

- [ ] 5.1 新增 `app/services/eval/scorers/claim_llm_judge_scorer.py`，复用 `JudgeLLMClient` 和 judge 配置，验证可用/不可用路径
- [ ] 5.2 实现 Claim Judge prompt，输入输出 Claim、证据/trace、工具结果和 `gold_claims`，验证输出包含 `claim_id`、`verdict`、`prediction_label`、`prediction_reason`
- [ ] 5.3 将 `unscorable` 映射为 `prediction_label=null`，`unsupported/contradicted` 映射为 true，`supported` 映射为 false，验证分类映射测试通过
- [ ] 5.4 将 `claim_llm_judge` 注册进 `scorer_hub`，作为独立评分器保存到 `eval_scores`，验证 `scorer_name/scorer_version` 正确
- [ ] 5.5 扩展指标聚合支持按 `scorer_name + scorer_version` 分流，验证规则型 Evidence Scorer 和 LLM Claim Judge 指标互不混算
- [ ] 5.6 验证 LLM 连续质量分不会写入 `prediction_label`，且缺少 Judge 依赖时返回 `not_configured`

## 6. 集成验证与文档

- [ ] 6.1 增加端到端测试：带 `gold_claims` 的 Case 创建 Run，跑出 Claim 预测后批量导入真值，再验证 metrics 返回真实 Precision/Recall/F1
- [ ] 6.2 增加有偏子集测试：只标注低置信度 Claim 时，metrics 展示抽样口径和覆盖率门禁，不输出可用全量指标
- [ ] 6.3 更新 `docs/hallucination-detection-metrics.md` 和 `docs/evaluation/agent-evaluation-platform-usage-and-gaps.md`，补充真值导入、review strategy、覆盖率和 LLM Claim Judge 工作流
- [ ] 6.4 运行 `pytest tests/test_hallucination_metrics.py tests/test_eval_platform.py tests/test_eval_phase2.py tests/test_eval_phase3.py`，验证相关评测测试通过
- [ ] 6.5 运行 `openspec validate --change add-claim-ground-truth-workflow --strict`，验证 planning artifacts 全部通过
