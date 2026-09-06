## Context

现有评测平台已经提供数据集版本、case 快照、run/trial、trace、评分器、趋势、release gate 和自进化 verify 能力，但 Skill 仍无法作为被系统验证的 artifact。`skill_route`/`skill_execute` 只存在于 `trace_adapter.py` 的事件类型中，runtime 没有发出真实事件；Skill 的选择由 LLM 通过 `load_skill` 隐式完成。需要在不引入显式路由层的前提下，先把路由决策、执行结果和共存影响变成可观察、可断言、可回归的评测对象。

## Goals / Non-Goals

**Goals:**
- 建立可观测的 Skill route/execute 事件契约，并复用现有 TraceAdapter。
- 为 EvalCase 增加 Skill 专用路由断言、执行断言和共存配置。
- 使用 `no_target_skill` 作为默认增量价值基线，并支持独立执行和完整 Skill 集合变体。
- 新增路由、执行和共存评分器，确定性断言优先。
- 将回归升级为配对 run 的逐 case 对比，并让 critical 回退阻断 promote。
- 保持旧 case、旧 trace、旧 run 和第三方 scorer 兼容。

**Non-Goals:**
- 不实现显式路由模块、Skill Tree 或策略路由。
- 不实现“什么经验值得沉淀成 Skill”的准入流程。
- 不改变 Skill 文件格式、加载优先级、工具权限或模型 provider。
- 不对全量 Skill 做两两共存全排列测试。

## Decisions

### 1. Skill 评测配置作为 `EvalCase` 的可选扩展，而非新集合

在 `EvalCase.scoring_criteria.skill_eval` 下新增可选配置，包括 expected_route、execution_asserts、coexistence、baseline_variant 和 critical。复用现有数据集版本、case 快照、run/trial 和 scorer 生命周期，避免为 Skill 评测维护第二套版本事实源。

**Alternative considered:** 新建独立 `skill_eval_cases` 集合。该方案隔离更清晰，但会复制版本、快照、回归和 scorer 逻辑，且不利于把 Skill case 和普通 case 放入同一 run。

### 2. 默认基线为 `no_target_skill`

默认评测基线只在运行时 Skill 集合中排除目标 Skill，保留其他 Skill、工具、系统 prompt 和模型不变。这样“加上目标 Skill”成为唯一变量，能回答增量价值问题。需要防止相似 Skill 补位造成污染，因此 case 同时声明 `disallowed_skills` 或只允许目标 Skill 触发的边界约束。

**Alternative considered:** 禁用全部 Skill。系统 prompt 和 Agent 行为变化过大，无法把结果差异归因到目标 Skill，且成本更高。

### 3. route 与 execute 事件在 runtime 显式 emit，而不是事后解析

在 `SkillsLoader` 构建描述、上下文注入 Skill 摘要、`LoadSkillTool.execute` 返回正文和 AgentLoop 完成关键执行时，分别发出 `skill_route` 和 `skill_execute` 事件。`skill_route` 记录候选 Skill、最终选中、未选原因或 `candidates_unavailable`；`skill_execute` 记录 Skill 正文是否加载、读取位置和关联 tool call。事件经现有 TraceAdapter 写入 `eval_trace_events`。

**Alternative considered:** 从最终输出反推 Skill 是否生效。该方案无法回答“加载了但没执行”和“执行了但没触发”的区别，且容易产生伪证据。

### 4. 路由判定区分 `route_selected` 与 `skill_effective`

`route_selected` 表示 `load_skill` 被调用或 route 事件明确选择目标 Skill；`skill_effective` 表示 Skill 正文加载后，后续工具调用、文件操作或输出确实遵循 Skill 断言。路由 scorer 分别计算，避免把“加载了但没起作用”当作触发成功，也避免“没加载但结果碰巧正确”掩盖静默绕过。

### 5. 执行断言采用“确定性优先，LLM 只兜底开放维度”

执行断言包括 required_tools、forbidden_tools、required_files、schema_checks、formula_checks、state_checks 和 output_structure。文件存在性、schema、字段、公式、工具调用记录和环境状态优先使用代码规则判断；只有报告完整度、表达质量等开放指标才允许进入 LLM judge。state_checks 通过比较 trial 前后状态快照或运行时记录的可观察副作用完成。

### 6. 共存测试首期使用人工挑选冲突对

在 Skill 评测数据集中预置描述相近、工具重叠、边界请求和多 Skill 协作场景，目标 Skill 与相邻 Skill 的候选组合由人工挑选。共存 scorer 比较完整 Skill 集合相对目标独立执行的成功率、触发分布和共享状态破坏情况，首期不做全量两两排列。

### 7. 配对回归 run 是独立一等对象

新增 `SkillRegressionGroup` 模型，保存 baseline_run_id、candidate_run_id、dataset_version、skill_baseline_version、skill_candidate_version、model_version、scorer_versions、critical_cases 和逐 case delta。回归指标按 case 聚合，并记录每个 case 的路由、执行、共存和最终输出维度变化。

回归门禁规则：
- critical case 任何维度回退 → block。
- 安全评分或确定性执行断言失败 → block。
- 非 critical 平均分回退 → 默认提示，可由管理员配置是否 block。

### 8. 回归结果接入自进化 verify/promote

`verification_service._compute_comparison` 不再只比较 run 级 success_rate，而是读取 `SkillRegressionGroup` 的逐 case delta 和 gate 结果。`promote_service` 在 critical 回退或执行断言失败时拒绝发布，并把阻断原因写入 receipt 和 Bad Case 回流记录。

### 9. 兼容性以可选字段和显式状态表达

`skill_eval`、Skill 版本、环境信息和回归引用全部可选。旧 case 没有配置时 scorer 返回 `not_configured` 或 `skipped`；旧 trial 没有 route/execute 事件时展示 `legacy_unverified`；旧 run 没有配对 run 时不进入 critical 门禁。

## Risks / Trade-offs

- [Risk] `no_target_skill` 基线可能被相似 Skill 补位 → Mitigation: case 声明 `disallowed_skills`，并在 route scorer 中把“应触发目标 Skill 却触发其他 Skill”判为失败。
- [Risk] runtime 事件量增加或事件顺序不稳定 → Mitigation: 只 emit route/execute 两类紧凑事件，并按 sequence、parent_event_id 和 skill name 建立索引。
- [Risk] 执行断言依赖真实外部数据源时不稳定 → Mitigation: 首期以工具调用记录和文件/schema 断言为主，真实数据状态断言按 Skill 配置开关启用。
- [Risk] 回归成本高 → Mitigation: 默认只对候选 Skill 相关 critical case 跑配对回归，普通 case 可配置为抽样。
- [Risk] LLM 对 Skill description 理解差异导致路由分数波动 → Mitigation: 记录模型版本并支持同一回归集在多个模型上运行。
- [Risk] 旧 promote 流程误用缺失回归结果 → Mitigation: Skill artifact promote 缺少配对回归结果时默认拒绝，除非管理员显式覆盖。

## Migration Plan

1. 先扩展 `EvalCase`、`EvalRunConfig` 和 trace 模型，字段全部可选。
2. 在 `SkillsLoader`、`context.py` 和 `LoadSkillTool` 中补 route/execute 事件，保持旧事件映射不变。
3. 新增 skill_route、skill_execution、skill_coexistence scorer，并在 scorer hub 注册。
4. 在 runner 中支持 `no_target_skill`、`skill_only`、`full_skill_set` 变体和 run snapshot。
5. 新增配对回归 run 模型、聚合服务和 API。
6. 接入自进化 verification/promote 门禁，先默认关闭或只对配置的 critical case 启用。
7. 补前端 trial 详情和 run 报告展示，旧数据显示不可用状态。
8. 运行模型、trace、scorer、runner、回归、门禁和兼容性测试。

**Rollback:** 关闭 Skill 评测 feature flag；runner 回退为默认单变体执行；trace adapter 保持旧事件映射；已写入的 `skill_eval` 字段和回归记录保留，不删除 Mongo 数据。

## Test Strategy

- 模型测试：`skill_eval` 配置、默认值、旧 case 兼容和 run snapshot。
- Trace 测试：`skill_route`/`skill_execute` 事件顺序、父子关系和缺失标记。
- Scorer 测试：路由命中/误触发/静默绕过、确定性执行断言、共存负影响。
- Runner 测试：三种变体下 Skill 集合隔离和版本快照。
- 回归测试：配对 run、逐 case delta、critical 阻断和普通回退配置。
- Evolution 测试：verify 消费回归结果，promote 拒绝 critical 回退。
- 前端测试：旧 trial 不报错，Skill 区域不可用时显示兼容状态。
