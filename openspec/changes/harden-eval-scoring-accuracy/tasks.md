## 1. 数据模型与评分状态

- [x] 1.1 在 `app/models/eval.py` 为 `ScoreStatus` 增加 `unscorable`、`not_applicable`，为 `ClaimVerdict` 增加 `unscorable`；验证新增枚举值可导入且旧枚举值保持不变（spec: Layered scoring）
- [x] 1.2 新增 `ClaimAnnotation` 模型，包含 annotation_id、reviewer、truth_label、hallucination_type、evidence_refs、comment、label_version、timestamp；为 `ClaimEvidence` 增加 `annotation_history` 和 `verification_method` 可选字段；验证模型支持历史记录和缺省兼容（spec: Claim truth annotation）
- [x] 1.3 在 `EvalScore` 或 `ScoreResult` 上明确保存 `scoring_status`，支持 `passed/failed/skipped/not_configured/error/unscorable/not_applicable`；验证 score summary 和 API 能区分新状态（spec: Layered scoring / Expected output）

## 2. 证据质量评分

- [x] 2.1 重构 `app/services/eval/scorers/evidence_scorer.py`，将 n-gram 重叠仅作为检索相关性信号，不再单独产生 `supported`；增加对抗测试：数字/实体/时间与证据矛盾但 n-gram 重叠高时不得判为事实 supported（spec: Evidence scoring must separate lexical similarity from factual support）
- [x] 2.2 为输出为空、无证据事件或证据不足的样本返回 `unscorable`/低置信，而不是高置信失败分；验证 score 和 claim 状态正确（spec: Layered scoring / No evidence event）
- [x] 2.3 增加结构化一致性检查，至少覆盖数字、股票代码、日期/时间窗口等可机械化字段，并在 `verification_method` 中记录检测方法；验证每个 claim 都返回判定原因和方法（spec: Evidence scoring must separate lexical similarity from factual support）
- [x] 2.4 实现矛盾检测：当证据与输出或两个证据存在可判定冲突时生成 `contradicted`，保存冲突证据引用和原因；验证矛盾样本返回 `contradicted`（spec: Contradiction predictions must be truthful）
- [x] 2.5 修正幻觉预测映射：未实现或未执行矛盾检测时不得把空状态映射成 `contradicted`；验证 `prediction_label` 不会产生虚假矛盾预测（spec: Contradiction predictions must be truthful）

## 3. LLM Judge

- [x] 3.1 为 `app/services/eval/scorers/llm_judge_scorer.py` 增加显式 `is_available`，删除 mock 回退；验证 SDK/模型不可用时 `ScorerHub` 写入 `not_configured` 而不是普通 0.5 分（spec: Judge dependency is unavailable）
- [x] 3.2 新增 JudgeContextBuilder，将 trace 中的 evidence/retrieval/citation、`expected_output`、数据窗口和 rubric 组装进 prompt；验证 prompt 包含可用证据或参考答案（spec: Judge-based open-ended scoring）
- [x] 3.3 让 `ScorerHub.score_trial` 接收 run config，并按 run 的 `judge_model`、`rubric`、`rubric_version` 实例化 Judge；验证运行指定配置会出现在 raw output 和保存结果中（spec: Judge-based open-ended scoring / design 3）
- [x] 3.4 在 `EvalScore.raw_output` 中保存 judge model、rubric version、prompt 摘要和原始响应；验证人工复核 API 能读取这些字段（spec: Judge-based open-ended scoring / design 3）

## 4. Expected Output 评分

- [x] 4.1 新增 `ExpectedContentScorer`，消费 `expected_output.must_include`、`scoring_criteria.required_fields`、`required_sections`、`forbidden_phrases`、`required_tool_types`；验证必含项全部命中才通过，缺失项会被列出（spec: Expected output must influence scoring）
- [x] 4.2 Case 无 `expected_output` 或对应标准时返回 `not_applicable`，不参与质量 pass；验证摘要和 pass 统计排除该维度（spec: Case has no expected output）
- [x] 4.3 将 `ExpectedContentScorer` 注册进 `ScorerHub` 并接入 run 的默认评分器列表；验证 golden case 中 `must_include` 能影响评分结果（spec: Expected output must influence scoring）

## 5. 指标与 pass@k

- [x] 5.1 在 `app/services/eval/metrics_service.py` 为 `compute_pass_at_k` 增加 `mode=quality/execution`；质量口径下只有有效评分通过才算 pass，完成但低分不算；验证 completed-but-failed 不被计为 pass（spec: Trial completes but fails scoring）
- [x] 5.2 保留执行口径并明确命名为 execution，接口响应返回 `mode` 字段；验证新旧口径不会互相覆盖（spec: Compute stability metrics）
- [x] 5.3 更新运行报告、趋势和 Release Gate 默认使用质量口径；验证报告显示的口径与接口返回值一致（spec: Compute stability metrics）
- [x] 5.4 更新分数聚合和复核队列，排除 `unscorable`、`not_applicable` 对平均分和 pass 统计的污染；验证新状态不会进入普通通过率分母（spec: Layered scoring / Expected output）

## 6. 数据集版本与 Run Snapshot

- [x] 6.1 修改 `app/services/eval/dataset_service.py`：`update_case` 插入新版本 case 文档而不是原地修改；验证更新后旧版本内容仍可查询（spec: Case is updated after run creation）
- [x] 6.2 修改 `delete_case` 为归档/软删除并保留历史版本；验证删除后历史 case 仍可通过旧版本读取（spec: Case is deleted after run creation）
- [x] 6.3 调整 `list_cases(version)` 为按每个 case 的目标版本选择最新可用版本；验证版本选择结果稳定（spec: Replay a dataset version）
- [x] 6.4 修改 `runner_service`，执行和评分使用 `run.snapshot.case_contents` 中的输入与 `scoring_criteria`，不再重新读取当前 case；验证 run 创建后修改/删除 case 不影响该 run（spec: Case is updated after run creation / design 7）
- [x] 6.5 在 run 和 trial API 返回 snapshot version 和输入来源标识；验证历史重放能看到锁定版本（spec: Replay a dataset version）

## 7. Claim 真值与多人标注

- [x] 7.1 更新 Claim 标注 API，支持保存结构化 `evidence_refs` 并写入 `annotation_history`；验证每次标注都留下 reviewer、版本、原因和时间（spec: Save a labeled claim）
- [x] 7.2 强化幻觉指标元数据校验：缺少 `truth_source` 或 `label_version` 的 Claim 不参与 Precision/Recall/F1；验证 excluded 数量和原因正确（spec: Missing annotation metadata）
- [x] 7.3 为多人标注增加一致性聚合：无一致性结论时返回 `not_available`，不静默取单条标签；验证分歧样本不会输出单值指标（spec: Multiple annotations disagree）
- [x] 7.4 在人工复核 API 和评测后台展示 claim 标注历史、证据引用和一致性状态；验证前端字段存在并可通过现有页面查看（spec: Save a labeled claim / design 8）

## 8. 兼容性与前端

- [x] 8.1 更新 `app/routers/eval.py` 中 score summary、pending review 和 metrics 返回结构，兼容 `unscorable/not_applicable`；验证旧 API 字段仍保留（spec: Layered scoring / design 1）
- [x] 8.2 更新运行详情、运行报告和人工复核页，展示不可评分、Judge 未配置和质量 pass 口径；验证 `vue-tsc --noEmit` 通过（spec: Compute stability metrics / design 1）
- [x] 8.3 在 `docs/evaluation/scoring-reliability-issues.md` 增加指向本 change 的修复状态说明；验证文档链接和结论一致（spec: 文档记录，不改变行为）

## 9. 集成验证

- [x] 9.1 补齐并运行证据评分对抗样本、矛盾检测、Judge 缺失、ExpectedContentScorer、pass@k 口径和 snapshot 回放测试；验证 `pytest` 新增与既有评测测试全部通过（spec: 本 change 全部新增契约）
- [x] 9.2 增加端到端测试：创建 run 后更新/删除 case，再按 snapshot 重放，验证输入、评分标准和结果一致（spec: Case is updated after run creation）
- [x] 9.3 运行 `openspec validate --change harden-eval-scoring-accuracy --strict` 和既有评测测试；验证 OpenSpec change 与代码行为一致（spec: 本 change 可验证性）
