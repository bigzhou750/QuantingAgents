## 1. 数据模型与 Trace 契约

- [ ] 1.1 在 `app/models/eval.py` 或新增 `app/models/decision.py` 中定义 `DecisionRecordDoc`，字段覆盖决策 ID、business/task/session 引用、父决策、场景、候选选项、选择依据、最终结论、证据 ID、状态、置信度、版本和时间戳；通过模型单元测试验证字段默认值与旧数据兼容（spec: Agent must emit structured decision records; design: 1）
- [ ] 1.2 在 `app/services/eval/trace_adapter.py` 的 `TraceEventType` 中新增 `decision`，并为 `TraceEventDoc` 增加可选的 `business_id`、`task_id`、`session_id` 引用字段；通过现有 trace 模型测试验证旧事件读取不回归（spec: Evaluation trace must preserve decision records; design: 1, 2）
- [ ] 1.3 扩展 TraceAdapter 的事件映射、保存和查询，支持 `decision` 事件类型和按 task/business/session 查询，并为新字段建立复合索引；通过 trace adapter 测试验证索引、过滤和历史事件兼容（spec: Evaluation trace must preserve decision records; design: 2）

## 2. Runtime 与 TradingAgents 决策采集

- [ ] 2.1 在 Vibe runtime 事件 sink 中支持 emit `decision` 事件，把 AgentLoop 的关键决策输出为结构化记录并保留原 `tool_call`、`evidence` 事件；通过 runtime trace 测试验证事件顺序和父节点串联（spec: Agent must emit structured decision records; design: 3）
- [ ] 2.2 在 `tradingagents/graph/` 增加轻量决策采集 wrapper，覆盖分析师、研究员、研究经理、交易员和风险经理节点，输出场景、结论、依据、证据引用和状态；通过 graph fixture 测试验证多节点决策链可串联（spec: Agent must emit structured decision records; design: 3）
- [ ] 2.3 为工具调用生成候选工具记录，包含候选列表、选中工具、选择依据或 `candidates_unavailable`/`reason_unavailable` 标记；通过工具事件测试验证缺失理由时不编造依据（spec: Tool calls must expose candidate options and selection rationale; design: 4）
- [ ] 2.4 让 `VibeAgentService.ingest_worker_event` 将线上事件同步写入标准化 trace，携带 `business_id`、`task_id`、`session_id`，同时保留现有 `vibe_agent_events` 和 operation log；通过集成测试验证线上任务可回放完整 trace（spec: Unified audit chain must be queryable by business ID; design: 2）

## 3. 分层解释与一致性校验

- [ ] 3.1 新增 `ExplanationService`，基于决策记录、证据和最终输出生成开发者、业务、用户三层解释，并记录解释版本和来源；通过单元测试验证用户层不包含原始 reasoning 字段（spec: Layered explanations must match audience; design: 5）
- [ ] 3.2 新增 `ExplanationValidator`，比较解释、决策记录、证据和最终输出，输出 `consistent`、`inconsistent`、`unverifiable`、原因、置信度和校验器版本；通过单元测试覆盖三种状态和缺失输入（spec: Explanation consistency must be validated; design: 5）
- [ ] 3.3 将解释生成和校验接入任务完成链路，不一致结果进入待复核，缺失信息标记 `unverified` 且不阻断低风险结果；通过任务级测试验证解释字段、校验状态和复核任务创建（spec: Explanation consistency must be validated; design: 5, 8）

## 4. 统一审计服务与 API

- [ ] 4.1 新增 `DecisionAuditService`，按 `business_id`、`task_id` 或 `session_id` 聚合决策链、trace、证据、最终输出、操作日志引用、解释校验和人工复核记录；通过聚合测试验证同一业务对象的关联完整（spec: Unified audit chain must be queryable by business ID; design: 6）
- [ ] 4.2 新增统一审计只读 API，校验用户所有权或管理员权限，记录审计查询日志，并拒绝越权访问；通过 API 权限测试验证普通用户只能查自己的任务（spec: Unified audit chain must be queryable by business ID; design: 6）
- [ ] 4.3 对无决策链的历史数据返回 `legacy_unverified`，保留已有 trace 和日志；通过旧数据 fixture 测试验证响应结构和兼容性（spec: Unified audit chain must be queryable by business ID; design: 6）

## 5. 生产指标、告警与降级

- [ ] 5.1 新增决策链指标模型和聚合服务，输出完整率、解释一致性、证据覆盖率、审计查询延迟和高风险暂停次数，支持按时间/模型/策略/风险等级聚合；通过指标测试验证分子分母和空样本处理（spec: Production explainability metrics must be observable; design: 7）
- [ ] 5.2 将生产指标接入现有 governance 告警订阅和通知渠道，指标连续超过阈值时生成告警并暴露受影响业务 ID；通过告警检查测试验证阈值触发和关闭逻辑（spec: Production explainability metrics must be observable; design: 7）
- [ ] 5.3 新增 `explainability_mode` 配置、风险分级和降级策略：低风险任务保留结果并标记解释缺失，高风险任务暂停自主动作、保存原始 trace 并创建人工复核；通过降级测试验证两种模式（spec: Explainability failure must trigger safe degradation; design: 8）
- [ ] 5.4 将不一致、不可验证和高风险暂停样本接入现有 Bad Case 或人工复核队列，保存 business/task/session/决策链引用；通过复核 API 测试验证审计字段和回流动作（spec: High-risk decisions must have manual review fallback; design: 8）

## 6. 前端与评测后台展示

- [ ] 6.1 在自然语言研究工作台增加决策路径、候选比较、依据和证据下钻，普通用户只展示分层解释；通过前端 type-check 和关键交互测试验证无原始 reasoning 暴露（spec: Layered explanations must match audience; design: 5）
- [ ] 6.2 在评测 trial 详情和报告中展示决策链、解释校验状态、复核状态，以及缺少决策链时的不可用状态；通过前端 type-check 和组件测试验证旧 trial 不报错（spec: Evaluation trial details must expose explainability results; design: 6）
- [ ] 6.3 为管理员增加统一审计查看入口，展示按业务 ID 聚合的决策链、trace、证据、操作日志和复核记录；通过权限与页面测试验证管理员/研发可见、普通用户不可见（spec: Unified audit chain must be queryable by business ID; design: 6）
- [ ] 6.4 在 Bad Case 和线上抽样表单中保存并展示 `business_id`、`task_id`、`session_id` 和决策链引用；通过 API/UI 测试验证旧样本缺失引用时显示兼容提示（spec: Bad cases and online samples must retain audit references; design: 6）

## 7. 验证与文档

- [ ] 7.1 运行新增模型、trace、决策采集、解释校验、审计、指标、降级和权限相关测试，并验证旧评测测试不回归；使用 `pytest tests/` 中相关测试和 `openspec validate add-agent-decision-explainability-audit --strict` 检查（spec: 全部; design: Test Strategy）
- [ ] 7.2 在前端运行 `npm run type-check` 和相关组件测试，验证研究工作台、评测详情和管理员审计页面无类型错误；通过 `vue-tsc --noEmit` 和测试命令确认（spec: 前端展示相关; design: Migration Plan）
- [ ] 7.3 更新评测、研究工作和运维文档，说明决策链字段、解释层级、一致性状态、审计查询、指标口径和降级配置；通过文档审查确认与 spec/design 一致（spec: 全部; design: Migration Plan）
