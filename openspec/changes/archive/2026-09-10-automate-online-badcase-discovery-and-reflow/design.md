## Context

当前线上 Vibe Agent 会话的事件已经由 `ingest_worker_event()` 归一化并持久化，评测评分器也已具备规则、轨迹、证据、安全和 LLM Judge 能力。Bad Case 池和手动回流接口存在，但 `convert_to_case()` 会把线上坏输出直接写入 `expected_output`，且自动采集、去重、复核路由和按类型回流语义尚未建立。

本设计在现有模块上补齐线上样本治理层，不改变 Vibe Agent runtime 执行链路，也不引入新的外部评测平台。

## Goals / Non-Goals

**Goals:**
- 在不阻塞线上会话的前提下，自动生成 Bad Case 候选并保存可解释的检测信号。
- 将高置信硬失败自动入池，将低置信质量信号和风险样本路由到复核队列。
- 对 Bad Case 去重，保存来源上下文，并按失败家族回流为语义正确的评测样本。
- 保持现有手工 Bad Case API、页面和旧数据兼容。
- 让 Bad Case 入池事件可以进入现有自进化 trigger，但不直接修改生产 artifact。

**Non-Goals:**
- 不实现自动审批、自动发版或自动回滚。
- 不重做 Vibe Agent runtime、SSE 和任务中心。
- 不新增外部评分框架作为硬依赖。
- 不在本 change 中建立完整金融数据历史快照系统，只保存数据窗口引用并标记不可回放状态。

## Decisions

### 1. 线上判定采用“事件接入 + 后台异步评分”

在 `ingest_worker_event()` 中保留轻量硬信号识别，例如 `attempt.failed`、`attempt.cancelled`、空输出和权限拒绝。需要 LLM Judge、证据或轨迹评分的候选进入异步后台任务，避免线上 SSE 和任务中心等待评分完成。

备选：直接把线上会话作为 eval trial 串进评测运行。该方案会耦合生产执行与评分延迟，且会把评测资源消耗放大到全量线上流量，因此不采用。

### 2. 使用单一 Bad Case 集合保存候选和已确认样本

在现有 `EvalBadCase` 上增加可选字段，而不是新建平行集合：

- `detection_status`: `candidate` / `confirmed` / `rejected`
- `review_status`: `pending` / `approved` / `rejected` / `auto_confirmed`
- `failure_family`
- `detection_signals[]`
- `detection_confidence`
- `dedup_key`
- `source_context`
- `reflow_status`

手工 API 创建的记录默认 `detection_status=confirmed`、`review_status=manual`，保持现有行为。自动候选先以 `candidate` 保存，复核或高置信路由后转为 `confirmed`。

选择单一集合是因为 Bad Case 的生命周期连续，历史来源、复核结果和回流状态不应跨集合丢失。查询现有 Bad Case 列表时默认过滤或展示候选需由 API 明确区分。

### 3. 自动路由先硬后软

路由策略按以下优先级：

1. runtime 失败、空输出、明确权限违规 → `auto_confirmed`。
2. 安全风险标签 → `confirmed` + `review_required=true`。
3. 明确用户反馈 → `candidate`，由复核人确认失败家族。
4. 多个规则/证据信号一致且置信度达标 → `auto_confirmed`。
5. 单一 LLM Judge 低分或偶发低质量 → `candidate` + Review Queue。
6. 低严重级别且无证据 → 仅更新统计指标，不创建 Bad Case。

LLM Judge 不单独决定自动入池，避免把 Judge 误判当作线上事实。

### 4. 去重指纹与重复合并

`dedup_key` 由规范化输入、失败家族、规范化失败特征、artifact 版本和数据窗口计算 SHA-256 哈希生成。自动创建前先查指纹：

- 命中已确认 Bad Case → 更新出现次数、受影响版本、最近会话和时间窗口。
- 命中候选 → 合并信号列表，避免重复复核。
- 未命中 → 创建新 Bad Case。

不同数据窗口和 artifact 版本视为不同样本，因为失败可能由版本或外部数据变化引起。

### 5. 回流使用策略化转换，而不是坏输出复制

保留 `convert_to_case()` 入口，但内部改为 `reflow_with_policy()`：

- 执行失败 → 只写输入和 `scoring_criteria`，不写 `expected_output`。
- 工具/轨迹失败 → 在 `scoring_criteria` 中表达失败约束。
- 证据/幻觉问题 → 保存 label、失败家族和评分规则，`expected_output` 保持为空。
- 安全样本 → 人工确认前只允许进入安全回归池或复核队列。
- 用户反馈 → 无正确参考答案时保持为负向样本，等待人工修订。

该决策修正了当前“坏输出 = 期望输出”的数据污染问题。

### 6. 数据集分层通过 dataset metadata 表达

复用现有 `EvalDataset.metadata`，新增 `purpose` 字段：

- `online_regression`
- `review_queue`
- `detector_eval`
- `golden`

每个 Bad Case 回流目标由失败家族、复核状态和置信度共同决定，而不是统一写入同一数据集。每次回流继续复用现有 patch 版本递增逻辑。

### 7. Bad Case 事件通过 trigger 服务进入自进化

Bad Case 创建、确认或升级后调用 `trigger_service.on_bad_case_event()`。该入口复用现有阈值、冷却窗口和去重逻辑，只在满足条件时创建 proposal。自动收集失败不得直接 promote。

## Risks / Trade-offs

- [自动判定产生噪音] → 使用多信号路由、置信度阈值和 Review Queue，不把单一 Judge 低分直接入池。
- [后台评分增加资源成本] → 支持采样率、配置开关和评分器选择，初期只对硬失败和低采样率输出做全量分析。
- [敏感数据进入 Bad Case] → 复用现有脱敏规则，保存前清洗；大文本使用摘要或外存引用。
- [金融数据不可完整回放] → 保存数据窗口并标记 `replayable=false`，评测只验证结构与失败约束，不把当前事实当历史真值。
- [旧 API 行为变化] → 手工创建保持兼容；回流接口内部语义修正属于预期 bug 修复，通过测试覆盖。
- [去重指纹过强或过弱] → 指纹参数可配置，指纹变化通过版本字段记录。

## Migration Plan

1. 先扩展模型字段和索引，保持旧数据反序列化兼容。
2. 增加配置开关和采样率，默认只启用硬失败自动识别。
3. 接入 `ingest_worker_event()`，将明确失败写入候选/已确认 Bad Case。
4. 实现去重和检测信号保存。
5. 实现 `reflow_with_policy()` 和数据集分层。
6. 接入 Review Queue、用户反馈 API 和前端反馈入口。
7. 接入 `trigger_service.on_bad_case_event()`。
8. 最后放开软质量评分信号，并用人工确认率校准阈值。

回滚策略：关闭自动采集开关后，线上链路退回现有行为；新增字段不会阻止旧流程运行，旧 Bad Case 仍可手工查看、复核和转换。

## Open Questions

- 默认采样率按会话、用户还是 artifact 版本计算。
- LLM Judge 的自动复核阈值和置信度组合是否需要分环境配置。
- 用户反馈是否保存原始文本，还是只保存脱敏摘要和反馈类型。
- Online Regression Set 的默认 dataset id 和命名规则是否需要在首次部署时固定。
- 金融数据快照能力是否由另一个独立 change 引入，本 change 只保存引用。
