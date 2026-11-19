## Context

本变更建立在 Vibe Agent runtime 接入 QuantingAgents 的基础上，测评对象限定为 Vibe Agent runtime 的 AgentLoop、tools、skills、Swarm、trace、memory 和最终研究报告。现有系统使用 Python/FastAPI、MongoDB、Redis、Vue 3 和 Element Plus；测评平台应复用现有认证、任务、SSE、审计和用户隔离能力，并使用独立路由、任务类型和运行目录。

生产级 Agent 测评需要同时覆盖离线回归、线上观测、trace 回放、LLM-as-judge、规则评分、人工复核、安全红队和 bad case 回流。市场框架可作为加速器，但金融业务评测集、rubric、权限边界和核心结果数据必须保留在 QuantingAgents 内部。

## Goals / Non-Goals

**Goals:**

- 建立可复现、可对比、可回归的 Vibe Agent runtime 评测平台。
- 支持后台页面和内部 API 两种入口，页面负责治理可视化，API 负责自动化运行和未来 CI 接入。
- 统一保存评测集、case、run、trial、trace、score、judge result、human review、bad case 和报告。
- 支持 outcome eval 与 trajectory eval，并能定位失败来自模型、工具、数据、证据、权限、Prompt、Skill、Swarm 或运行时。
- 支持可插拔评分器，包括规则评分、金融规则评分、证据评分、安全评分、LLM-as-judge 和人工复核。
- 预留 Langfuse/Phoenix 观测适配、DeepEval/Ragas 评分适配和 Promptfoo 红队适配。

**Non-Goals:**

- 不评测现有单股分析和批量分析链路。
- 不在一期强制接入 CI 或发布门禁。
- 不把第三方观测平台作为唯一事实存储。
- 不允许测评任务绕过 QuantingAgents 的用户权限、工具权限和运行目录隔离。
- 不在本变更中训练或微调底层模型。

## Decisions

### Decision: 核心 EvalOps 自研，市场框架作为适配层

QuantingAgents 内部实现评测集、运行、trial、评分、复核、报告和 bad case 的核心数据模型；Langfuse/Phoenix、DeepEval、Ragas、Promptfoo 通过适配器接入。

理由：
- 金融测评标准、权限、审计和用户数据具有业务敏感性，不能完全外包给外部平台。
- 第三方框架能力边界不同，单一框架难以同时覆盖 Agent trace、金融 rubric、安全红队和后台治理。
- 自研核心模型可以避免平台锁定，同时保留后续替换观测/评分工具的空间。

替代方案：
- 完全使用 Langfuse/Braintrust 作为主平台：落地快，但业务数据模型、权限和报告会被平台形态限制。
- 全部自研：控制力强，但会重复建设 tracing、experiments、judge 和可视化能力，成本较高。

### Decision: 评测运行以 case trial 为最小可审计单位

每个 eval case 可以运行 N 次 trial。trial 保存独立输入、输出、trace、状态、耗时、token、错误、分数和复核结果。

理由：
- Agent 单次成功不能代表稳定成功，必须支持 pass@k、pass^k 和方差。
- trial 是定位非确定性失败、工具波动和模型退化的基本单位。
- 失败 trial 必须保留，不能被重跑覆盖。

### Decision: Trace Adapter 统一 Vibe 运行轨迹

新增 Agent trace 标准化层，将 Vibe Agent runtime 的事件归一为统一事件模型，例如 `llm_call`、`tool_call`、`skill_route`、`skill_execute`、`swarm_step`、`retrieval`、`memory_read`、`memory_write`、`evidence`、`final_report`、`error`、`safety_check`。

理由：
- 评分器不能直接依赖 Vibe 内部 trace 的不稳定格式。
- 统一 trace 后才能实现回放、失败聚类、工具评分、证据评分和观测平台导出。
- 大文本、敏感输入输出和证据快照保存为受控引用，观测平台仅接收摘要和引用。

### Decision: ScorerHub 采用插件式评分器

后端提供统一评分器接口，所有评分器输出统一结构：分数名称、分数、是否通过、原因、置信度、来源、版本和可选证据引用。

评分器分层：
- `RuleBasedScorer`：schema、字段、格式、token、耗时、工具调用、权限、超时。
- `FinancialScorer`：股票代码、日期、币种、单位、财务指标、数据新鲜度、风险披露。
- `EvidenceScorer`：证据覆盖率、引用相关性、无证据断言、来源一致性。
- `TraceScorer`：工具选择、参数正确性、步骤效率、重试、循环、空结果处理。
- `SafetyScorer`：提示注入、越权工具、敏感信息、投资建议越界。
- `LLMJudgeScorer`：答案完整性、金融推理、证据相关性、结论保守性。
- `HumanReviewScorer`：人工覆盖、边界样本校准和最终复核意见。

理由：
- LLM-as-judge 适合开放质量判断，但不适合替代确定性约束。
- 金融领域必须将数字、日期、权限、工具参数和审计交给程序侧校验。
- 插件式接口便于后续接入 DeepEval、Ragas、Promptfoo 或自研评分器。

### Decision: LLM-as-judge 必须版本化和可复核

LLM judge 固定 judge model、rubric、prompt、输出 JSON schema 和评分维度版本。低置信、高风险、分数边界和业务关键样本进入人工复核队列。

理由：
- judge 模型本身会有偏差和波动，需要与业务专家样本持续校准。
- 保存 judge 版本才能比较历史评测结果。
- 人工覆盖必须保留原始 judge 结果，避免审计断链。

### Decision: 后台页面负责治理，内部 API 负责自动化

后台页面用于管理评测集、发起运行、查看指标、回放 trace、复核分数、维护 bad case 和查看趋势。底层能力通过内部 API 和 service 实现，支持未来定时任务、批量回归和 CI 接入。

理由：
- 只有页面会导致自动化能力不足。
- 只有脚本会导致复核、治理和跨角色协作困难。
- API-first 能同时满足研发自动化和管理员可视化。

### Decision: 分三期交付

一期交付 Eval 基础设施 MVP：评测集、run、trial、trace、基础评分和后台基础页面。

二期交付质量评分与复核：LLM-as-judge、金融 rubric、DeepEval/Ragas 适配、人工复核、pass@k/pass^k、版本对比和 bad case 回流。

三期交付生产治理：Langfuse/Phoenix 观测适配、Promptfoo 红队、online eval 抽样、安全评测、趋势告警和可选 release gate。

## Risks / Trade-offs

- [Risk] 评分器过松或过严导致结果失真 → Mitigation: 评分器版本化、人工抽检、低置信样本复核和 judge 校准集。
- [Risk] trace 数据包含敏感信息或体量过大 → Mitigation: 大文本和敏感内容保存到受控存储，观测平台只接收摘要、脱敏字段和引用。
- [Risk] 评测结果依赖实时金融数据导致不可复现 → Mitigation: case 绑定时间窗口、数据快照引用和数据源版本。
- [Risk] LLM-as-judge 成本较高且有波动 → Mitigation: 先用规则评分过滤，必要维度再调用 judge；固定 judge model 和 prompt 版本。
- [Risk] 只看总分掩盖关键安全回退 → Mitigation: 报告以分维度指标、失败样本和风险标签为主，不以单一总分作为唯一判断。
- [Risk] 第三方框架能力或许可变化影响平台 → Mitigation: 通过适配器接入，核心数据模型和业务流程不依赖单一框架。
- [Risk] 评测运行影响正常 Agent 服务资源 → Mitigation: 独立任务类型、并发限制、预算限制、超时和取消机制。

## Migration Plan

1. 新增评测平台配置项，默认关闭后台入口和自动运行。
2. 部署一期数据模型、API、runner 和后台页面，不影响现有用户路径。
3. ���用少量 golden set 进行内部试运行，校准 trace 和基础评分器。
4. 扩展 LLM judge、人工复核和 bad case 回流后，再开放给研发/管理员常态使用。
5. 第三期按需启用 Langfuse/Phoenix、Promptfoo 和线上抽样；所有外部平台接入可配置关闭。

回滚策略：
- 关闭评测平台配置即可停止新建 eval run。
- 保留历史评测数据和 trace 引用用于审计。
- 不需要迁移或回滚现有单股分析、批量分析和自然语言研究工作台数据。

## Open Questions

- 一期是否优先接 Langfuse 还是 Phoenix，取决于部署偏好和团队是否更重视自托管 UI 还是 OpenTelemetry/OpenInference 标准化。
- LLM judge 默认模型、成本预算和人工复核比例可在实现前结合现有模型供应商配置确定。
- 金融 golden set 的首批 30-50 条 case 需要由业务侧和研发共同确认覆盖范围。

