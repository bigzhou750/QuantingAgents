## 1. 数据模型与兼容

- [x] 1.1 扩展 `app/models/eval.py` 的 `EvalBadCase`，增加 `failure_family`、`detection_signals`、`detection_confidence`、`detection_status`、`review_status`、`dedup_key`、`source_context`、`reflow_status` 等可选字段，并验证旧 Bad Case 文档可正常反序列化
- [x] 1.2 定义 `failure_family` 枚举和 `DetectionSignal` 模型，包含 `signal_type`、`failure_family`、`score`、`confidence`、`severity`、`reason`、`evidence_refs`、`detector_name`、`detector_version`，并验证枚举和模型测试通过
- [x] 1.3 在 Bad Case 集合增加 `dedup_key`、`detection_status`、`review_status`、`created_at` 索引，并验证初始化可重复执行且旧索引不受影响
- [x] 1.4 在 `app/core/config.py` 增加自动采集开关、采样率、Judge 阈值、证据阈值和数据集分层配置，并验证配置默认值读取正常

## 2. 自动发现与判定

- [x] 2.1 实现“线上会话到 pseudo-trial”的适配器，将 session/task/final output/trace 转成现有 scorer 可接受的输入，并验证 `trace_adapter` 事件映射可用
- [x] 2.2 实现硬失败检测：`attempt.failed`、runtime 失败、超时、空输出、缺少最终结果，并验证对应检测信号可生成
- [x] 2.3 实现可选软信号检测：工具轨迹、证据质量、安全规则、LLM Judge 和用户反馈，并验证各检测器失败时不会阻断原始会话
- [x] 2.4 实现 `OnlineBadcaseAdjudicator` 合并信号并按路由策略输出 `auto_confirmed`、`review_required` 或 `metric_only`，并验证各路由分支测试通过
- [x] 2.5 在 `app/services/vibe_agent/service.py` 的 `ingest_worker_event()` 接入异步候选生成，并验证线上失败会创建 Bad Case 候选且 SSE/任务中心不受影响
- [x] 2.6 实现采样率和并发控制，默认硬失败全量采集、软质量信号按配置采样，并验证超限样本只记录指标

## 3. 去重与上下文

- [x] 3.1 实现 `dedup_key` 生成，基于规范化输入、失败家族、规范化失败特征、artifact 版本和数据窗口，并验证相同输入不同失败家族生成不同指纹
- [x] 3.2 实现重复 Bad Case 合并：更新出现次数、受影响版本、最近会话和时间窗口，不重复创建记录，并验证合并测试通过
- [x] 3.3 在 Bad Case 创建时保存 `source_context`，包含脱敏用户标识、session、task、trace、数据窗口、artifact 版本和发布回执引用，并验证上下文可查询
- [x] 3.4 实现敏感信息脱敏和大文本截断，复用现有观测平台脱敏规则，并验证凭证和手机号等模式不会原样写入 Bad Case

## 4. 用户反馈

- [x] 4.1 新增研究工作台用户反馈 API，要求合法用户、session 和 task 上下文，并验证缺少上下文时拒绝或仅保存脱敏独立反馈
- [x] 4.2 在前端研究工作台增加“回答错误”“内容无用”“提交反馈”入口，并验证反馈提交成功后出现状态反馈
- [x] 4.3 将反馈接入 Bad Case 候选创建和去重流程，并验证反馈原文、任务、输出版本和检测信号正确关联

## 5. 复核与兼容

- [x] 5.1 扩展 Bad Case 列表/详情 API，展示 `detection_status`、`review_status`、`detection_signals` 和 `source_context`，并验证旧字段缺失时返回兼容结构
- [x] 5.2 新增 Review Queue API，支持按候选列表、复核通过、复核拒绝和更新标签，并验证状态流转和权限校验
- [x] 5.3 更新 Bad Case 后台页面，展示检测信号、复核状态和失败家族，并验证前端类型检查和组件测试通过
- [x] 5.4 保持 `/api/eval/online-sample` 和现有手工 Bad Case 接口兼容，并验证旧请求结构仍可创建记录

## 6. 可靠回流

- [x] 6.1 实现 `reflow_with_policy()`，按失败家族选择回归 Case、负向 Case、标签样本或人工修订样本，并验证任何路径都不会把原始坏输出写入 `expected_output`
- [x] 6.2 实现执行失败和工具失败回归 Case 构建器，将超时、空输出、权限违规和死循环转成 `scoring_criteria`，并验证对应 Case 结构
- [x] 6.3 实现证据和幻觉样本构建器，保存 `truth_label`、幻觉类型、失败规则和检测信号引用，并验证缺少人工真值时不会自动生成错误期望输出
- [x] 6.4 实现安全样本回流门禁，要求人工确认和标签版本后才允许进入正式数据集，并验证未确认样本不会进入 Golden Set
- [x] 6.5 在回流时保存 `reflow_from_bad_case_id`、来源上下文和检测信号，并验证数据集 patch 版本正确递增
- [x] 6.6 为数据集增加 `purpose` 元数据：`online_regression`、`review_queue`、`detector_eval`、`golden`，并验证按 purpose 查询和写入隔离

## 7. 触发自进化

- [x] 7.1 在 `app/services/evolution/trigger_service.py` 增加 `on_bad_case_event()`，复用阈值、冷却和去重逻辑，并验证达到阈值时才创建 proposal
- [x] 7.2 对 high/critical Bad Case 增加升级事件，并验证升级不会直接 promote 或修改生产 artifact
- [x] 7.3 验证自进化关闭、冷却窗口生效或重复指纹存在时，Bad Case 仍可收集且触发被抑制的原因被记录

## 8. 文档与集成验证

- [x] 8.1 更新 `docs/evaluation/online-badcase-automation-and-reflow-design.md`，补充自动判定、复核、回流和触发实现说明
- [x] 8.2 补充 API 文档，覆盖反馈提交、Review Queue、自动采集配置和回流接口变更
- [x] 8.3 运行 Bad Case、数据集、Vibe Agent 事件、评测 scorer、自进化 trigger 相关测试，并验证无回归
- [x] 8.4 运行 `openspec validate automate-online-badcase-discovery-and-reflow --strict`，并验证所有 planning artifact 通过
