## Context

现有 Vibe runtime 事件、评测 trace、TradingAgents graph 决策和操作审计分别存储，缺少统一决策节点契约。Vibe runtime 已通过事件流暴露 `tool_call`、`evidence`、`react_summary` 等事件；`TraceAdapter` 能把事件标准化并保存到 `eval_trace_events`；`tradingagents/graph/signal_processing.py` 只把最终交易结论抽取为 action、reasoning 等字段；线上 Vibe 事件和工具操作日志按 session/task 存储，但无法一键聚合为可审计决策链。

## Goals / Non-Goals

**Goals:**

- 建立跨 Vibe runtime、TradingAgents graph 和评测平台统一的 `decision` trace 契约。
- 为工具调用和业务结论保存候选选项、选择依据、结论、证据和版本信息。
- 提供分层解释、解释一致性校验和按业务 ID 的统一审计查询。
- 提供生产指标、告警和高风险场景的降级与人工复核能力。
- 保持现有 API、评测流程、权限模型和第三方 scorer 兼容。

**Non-Goals:**

- 不改变现有模型 provider、工具注册、Swarm 语义或交易图拓扑。
- 不把原始模型思考过程直接暴露给终端用户或普通业务页面。
- 不重新实现现有 Claim-Evidence 评分和幻觉指标，只复用其结果作为校验输入。
- 不在本设计中引入新的训练数据集、专有模型或外部可解释性平台依赖。
- 不默认允许新的自动交易或写操作；高风险“可执行结果”仍受现有合规边界约束。

## Decisions

### 1. 新增 `decision` trace 事件作为唯一决策节点契约

在 `TraceEventType` 中新增 `decision`，`DecisionRecordDoc` 保存决策 ID、business/task/session 引用、父决策、决策场景、候选选项、选择依据、最终结论、证据 ID、状态、置信度、模型/策略版本和时间戳。Vibe runtime、TradingAgents graph 和工具链都向该模型输出，而不是各自维护私有日志。

**Rationale:** 现有 trace adapter 已经是跨 runtime 与评测的统一入口；增加一个事件类型比另建一套决策存储更贴近现有架构，也能让评测 trial 直接回放生产决策链。

**Alternative considered:** 单独建 `agent_decision_chains` 集合，不依赖 trace 事件。该方案便于聚合，但会让线上 trace 与评测 trace 产生第二份事实源，审计一致性更差，因此不采用。

### 2. 生产 Vibe 事件与评测 trace 共用 TraceAdapter

`VibeAgentService.ingest_worker_event` 在保存 `vibe_agent_events` 的同时，通过 TraceAdapter 写入标准化 trace，并为 TraceEventDoc 增加 `business_id`、`task_id`、`session_id` 字段。评测 runner 继续使用同一适配器，但以 `trial_id` 为主索引，两者可互相引用。

**Rationale:** 线上审计与离线评测使用同一事件归一逻辑，避免线上用原始 payload、评测用标准化 payload 导致行为不一致。

### 3. 决策记录采用“运行时注入 + 结构化提取”双通道

Vibe runtime 在产生 agent 决策和工具调用时尽量直接 emit `decision` 事件；TradingAgents graph 通过轻量 wrapper 在分析师、研究经理、交易员、风险经理等节点收尾时记录决策。模型未输出选择理由时，后续解释服务可以尝试结构化提取，但 MUST 标记 `reason_unavailable` 或 `unverified`，不能编造候选和依据。

**Rationale:** 不能依赖模型原生可解释能力；外层结构化提取是兜底，不是替代。直接 emit 优先保证真实链路，提取兜底只用于补全缺失信息。

### 4. 工具决策记录候选列表而非只记录调用结果

工具调用事件在生成 `decision` 时使用该节点可见的工具注册表作为候选集，并尝试从模型消息、tool call 元数据或后续结构化提取中获取“为什么选 A 不选 B”。若候选集合不可用，标记 `candidates_unavailable`。

**Rationale:** 笔记中的核心追问是“为什么从三个工具中选了这个、拒绝另外两个”，只存最终调用无法回答该问题。

### 5. 分层解释与一致性校验作为独立服务

新增 `ExplanationService` 和 `ExplanationValidator`。前者根据决策记录、证据和最终输出生成开发者/业务/用户三层解释；后者比较解释、决策记录和证据，输出 `consistent`、`inconsistent`、`unverifiable` 及原因。原始模型 reasoning 只允许写入受控的原始审计引用，不进入用户层解释。

**Rationale:** 业务理由可能“听起来合理但和真实决策不符”，必须由校验器拦截，不能把生成解释等同于可信解释。

### 6. 统一审计服务按 business ID 聚合

新增 `DecisionAuditService`，以 `task_id` 为默认业务主键，兼容 `business_id` 和 `session_id` 别名，聚合决策记录、标准化 trace、证据、最终输出、操作日志引用、解释校验和人工复核记录，对外提供统一只读接口。查询必须校验用户所有权或管理员权限，并记录审计日志。

**Rationale:** 现有 API 分别按 session/trial/task 查询，无法回答“业务单据对应哪条决策链”；统一聚合接口是审计追溯的一键入口。

### 7. 生产指标复用现有评测治理配置

新增决策链指标模型，聚合完整率、解释一致性、证据覆盖率、审计查询延迟和高风险暂停次数，写入 Mongo 指标集合并支持按模型/策略/风险等级聚合。告警复用现有 governance config 和通知渠道，不新增独立告警系统。

**Rationale:** 项目已有评测 gate、告警订阅和观测配置，生产指标可以复用其阈值、订阅和页面入口，避免重复建设。

### 8. 降级采用显式风险分级和 feature flag

新增 `explainability_mode` 配置和风险分级规则。解释模块异常时，低风险任务保留结果并标记解释缺失；高风险任务暂停后续自主动作、保存原始 trace 并创建人工复核任务。由于项目当前不执行实盘交易，风险分级用于控制高风险输出、写操作和未来可执行动作，具体规则由管理员配置。

**Rationale:** 没有降级路径的可解释系统在故障时会把高风险任务继续交给黑盒输出，这不符合笔记边界。

## Risks / Trade-offs

- [Risk] 模型不输出工具选择理由，结构化提取可能生成看似合理但错误的理由 → Mitigation: 缺失时标记 `unverified`/`reason_unavailable`，解释校验不一致时进入人工复核，不直接展示为事实。
- [Risk] 额外解释和校验增加延迟与成本 → Mitigation: 低风险或普通用户场景使用规则摘要和缓存，完整校验可配置为仅高风险、审计或管理端任务。
- [Risk] 生产 trace 与评测 trace 统一后事件量增大 → Mitigation: 决策记录保持紧凑字段，原始大对象继续外存或脱敏引用，Mongo 增加 task/business/trial 复合索引。
- [Risk] 历史数据缺少决策链和解释字段 → Mitigation: 新增字段全部可选，查询和 UI 对旧数据返回 `legacy_unverified`，不参与一致性指标分母。
- [Risk] 原始推理内容被误暴露 → Mitigation: 原始 reasoning 存受控审计引用，分层解释只输出面向受众的内容，前端权限校验和脱敏测试覆盖该路径。
- [Risk] 现有评测评分把缺解释当成低分 → Mitigation: 沿用 `skipped`、`not_configured`、`error` 状态，缺决策链不改变旧 scorer 语义。

## Migration Plan

1. 先扩展数据模型和 TraceAdapter，保持旧事件映射不变，新增 `decision` 事件类型及业务引用字段。
2. 接入 Vibe runtime 决策 emit、TradingAgents graph 决策采集和工具候选记录，默认在新增链路生效，旧路径保留兼容。
3. 新增解释、校验、审计聚合、指标和降级服务，并用配置开关控制高风险暂停行为。
4. 接入前端研究工作台、评测 trial 详情和审计页面，对旧数据展示不可用状态。
5. 补充后端单元测试、trace/audit 集成测试、权限测试、降级测试和前端 type-check。
6. 文档更新后先开放内部/测试环境，再按 feature flag 分阶段启用生产决策链和降级策略。

**Rollback:** 关闭 `EXPLAINABILITY_ENABLED`、`DECISION_AUDIT_ENABLED` 和降级策略开关；VibeAgentService 回退为仅写原事件集合，TradingAgents graph 不注入决策采集 wrapper，保留已写数据供后续审计查看。不使用删除 MongoDB 数据的方式回滚。

## Test Strategy

- 模型与 schema：覆盖 DecisionRecord、TraceEventDoc 业务引用、解释版本、校验状态和旧数据兼容。
- Trace adapter：验证 Vibe 事件映射到 `decision` 后不破坏已有 `tool_call`、`evidence` 等事件。
- 决策采集：验证 Vibe runtime 和 TradingAgents graph 的决策节点顺序、父节点、候选选项和缺失标记。
- 解释与校验：覆盖一致、不一致、不可验证、原始 reasoning 不进入用户层。
- 审计接口：覆盖按 task/business/session 查询、用户隔离、管理员权限、旧数据 `legacy_unverified`。
- 降级：覆盖解释模块异常时低风险继续、高风险暂停并生成人工复核。
- 评测兼容：覆盖旧 trial 无决策链时不改变既有评分和复核流程。
