## Context

`docs/evaluation/claim-extraction-optimization.md` 列出的问题分散在评测平台、决策审计、线上 Bad Case 和自进化运营链路中。当前实现里，`EvidenceQualityScorer._extract_claims()` 直接按 `[。！？.!?\n]` 切句并取前 20 条；`LLMJudgeScorer` 默认 `qwen-plus` 且 `is_available` 只检查 dashscope；`runner_service.create_run()` 构建 snapshot 时没有把 `case_id` 写入 value；`DecisionAuditService.build_audit()` 只返回 `legacy_unverified/unavailable`；`OnlineBadcaseService` 直接散落读取 `settings.ONLINE_BADCASE_*`；发布后观测只有后端接口，没有管理页面。详见 `proposal.md - Why` 和 `specs/` 下的行为契约。

## Goals / Non-Goals

**Goals:**

- 用一个 change 覆盖从 Claim 输入、Judge 通道、Run 初始化、审计展示、Bad Case 配置到发布后观测的完整评测运营链路。
- 优先扩展现有数据模型和 API，保持旧字段、旧客户端和已有页面可读。
- 让不可评估、未配置、未生成和初始化失败都成为显式状态，不再被静默当作失败或正常结果。
- 为线上 Bad Case 和发布后观测提供可审计的运营界面，而不改变现有闭环语义。

**Non-Goals:**

- 不重写 Vibe Agent runtime、普通研究工作台或现有自进化提案/发布流程。
- 不在发布后观测第一版自动拉取线上指标，也不在页面执行 rollback/stop。
- 不删除环境变量，只把运行时配置的默认值和覆盖层次理顺。
- 不引入新的外部评测框架或 Markdown 解析依赖。

## Decisions

### 1. Claim 抽取独立成可测试流水线

新增 `app/services/eval/claim_extraction/`，按文档的阶段顺序提供：

```text
原始输出
  -> 归一化
  -> 候选片段生成
  -> 片段合并与完整性检查
  -> Markdown/格式过滤
  -> Claim 候选排序
  -> 数量上限
  -> ClaimEvidence 构造
```

`EvidenceQualityScorer` 只调用 `extract_claims()` 并兼容转换到现有 `ClaimEvidence`。归一化阶段保留 `source_start/source_end` 或等价 span 字段，方便人工复核回看原文。合并只对可确定性恢复的跨行模式执行，例如 `600519\nSH`、`EPS` 被换行拆开、金额小数续行；无法确定的片段保留原文并标记 `excluded_reason`，不参与指标分母。

理由：现有抽取逻辑在 scorer 内部，无法单独测试和复用。独立模块可以让中文/英文/Markdown/跨行/截断样本全部变成纯函数测试。

替代方案：全部留在 `evidence_scorer.py`。更少文件，但会继续把抽取和证据打分耦合，回归面更大。

### 2. Markdown 过滤采用行级状态机

用行级分类器识别标题、fenced code block、Markdown 表格分隔线、引用块、水平分隔线和常见字段标签；完整列表项去列表标记后保留为 Claim 候选。表格正文仍按单元格内容进入候选判断，不因“包含表格”整体丢弃。

理由：评测输出以金融报告和 Markdown 为主，行级状态机足够覆盖文档列出的问题，且不需要新增依赖。

替代方案：引入完整 Markdown AST 解析器。能力更强，但增加运行时开销和依赖面，收益在该阶段不匹配。

### 3. LLM Judge 改为 adapter 注入

新增 `JudgeLLMClient` 协议和 adapter registry，`DashScopeJudgeClient` 保留为现有适配实现，`DeepSeekJudgeClient` 和 `OpenAICompatibleJudgeClient` 复用 `tradingagents/llm_clients` 中的统一客户端。`LLMJudgeScorer.__init__(judge_model=None, adapter=None)` 允许测试注入 mock，`is_available` 不再依赖 `import dashscope`。

默认模型解析集中在 `app/services/eval/judge_config.py`，从 `settings.EVAL_JUDGE_MODEL_DEFAULT` 或统一 `DEFAULT_LLM_MODEL` 读取，`scorer_hub`、runner 和 API 校验都调用同一解析器。`raw_output` 记录实际 `judge_model`、adapter、耗时、成功/失败原因；未配置或调用失败返回 `NOT_CONFIGURED/ERROR`，不允许静默回退旧默认值。

理由：文档明确要求“单一事实源”和 provider 解耦；adapter 注入还能让测试不依赖真实模型。

替代方案：直接改 `_call_judge` 调 DeepSeek。改动小，但会丢失既有 dashscope 兼容和可测试边界。

### 4. Run snapshot 契约与 preflight

`create_run()` 为每个 snapshot value 写入 `case_id`。`_resolve_run_cases()` 增加归一化 helper：

```text
value 有 case_id -> 直接使用
value 缺 case_id、key 可用 -> 从 key 补回
两者都缺失 -> CaseSnapshotValidationError
```

`start_run()` 在调度 `_execute_run()` 前执行同步 preflight，校验 snapshot 可解析、case 数量一致、`case_id` 唯一且非空、`input.prompt` 结构、scorer/judge 配置和超时范围。preflight 失败时将 Run 置为 `failed`，写入 `failure_stage=snapshot_validation/case_validation/configuration`、`error_code`、`error_message` 和 `preflight` 结构化结果，并返回 `started=false` 给 API。`_execute_run()` 也调用同一 preflight，防止旧代码直接启动后的后台路径仍裸抛异常。

理由：文档的 P0 是“创建成功不代表运行可执行”，同步 preflight 让调用方在启动请求中直接感知初始化失败。

替代方案：继续异步 background task 再更新失败状态。改动小，但页面仍要等一次后台失败，无法解决文档指出的反馈延迟。

### 5. 运行失败状态扩展

`EvalRun` 增加可选字段 `failure_stage`、`error_code` 和 `preflight`，枚举覆盖 `none`、`snapshot_validation`、`case_validation`、`runtime`、`scoring`、`aggregation`、`storage`。前端运行详情根据 `status=failed` 优先展示首屏失败卡片，再展示 Trial 进度。

理由：把“运行初始化失败”和“Trial 执行失败”分开，避免 `0/63 完成，0 失败` 掩盖运行器故障。

替代方案：新增 `preflighting` 状态。可以更精确，但当前前端和 API 对未知状态处理成本更高，先用字段表达。

### 6. 决策审计状态、分页与中文名

`DecisionAuditService.build_audit()` 返回 `complete`、`partial`、`events_without_chain` 或 `empty`，同时返回 `audit_counts`（task/session、运行事件数、trace 数、决策记录数、解释/校验/复核数）和 `scope`。旧状态 `legacy_unverified` 映射到 `events_without_chain`，`unavailable` 映射到 `empty`，前端和旧调用方按别名兼容。

新增 `GET /api/decision-audit/chains/{identifier}/events`，复用 `build_audit()` 的 task/session 解析和权限判断，从 `vibe_agent_events` 按 `sequence`/`created_at` 稳定排序后 `skip/limit`。事件响应为 `{items, page, page_size, total, has_more}`，并给每条事件附带 `event_name`。

`event_name` 服务端使用统一映射表，同时检查 `event_type` 和 `payload.phase`；例如 `tool_call + phase=tool_result` 映射为“工具返回”。未知事件保留原始类型。前端保留 fallback 映射，避免后端字段缺失时空白。

理由：审计页需要回答“有运行但没链”和“数据确实为空”，分页必须由后端承担，不能继续一次性 1000 条。

替代方案：只在 `build_audit()` 返回全量事件并由前端分页。实现更快，但大任务仍会超过上限，且无法稳定复用权限查询。

### 7. 线上 Bad Case 配置分层

新增 `OnlineBadcaseConfigService` 和 `online_badcase_configs` 集合。环境变量只在首次初始化或数据库不可用时作为默认值；数据库中的 `draft/published/archived` 版本成为运行时来源。服务提供：

```text
get_effective_config()
list_configs()
create_draft()
publish()
rollback()
```

配置服务使用进程内短 TTL 缓存保存最近有效发布版本，发布或回滚时主动失效。校验失败、缓存缺失或数据库不可用时 fail-closed：优先最近一次有效发布，没有则回退到“关闭自动发现”的安全默认值。`online_badcase_service.py` 中的 `collect_soft_signals()`、`OnlineBadcaseAdjudicator` 和 Collector hook 改为统一读取快照，不再直接读 `settings.ONLINE_BADCASE_*`。

管理 API 放在自进化模块下，GET 允许自进化访问者只读，POST/发布/回滚要求自进化配置管理权限，并记录 `updated_by`、`updated_at`、`change_reason` 和版本差异。

理由：业务人员需要在系统内调整采样率而不改部署环境；统一快照比散落读 settings 更容易审计和做一致性校验。

替代方案：直接开放现有 `settings` 更新接口。改动小，但无法满足版本化、回滚和运行时切换。

### 8. 发布后观测独立页面

新增 `frontend/src/views/Evolution/PostReleaseObservation.vue`，路由 `/evolution/observation`，侧边栏“自进化”菜单增加“发布后观测”。页面复用现有 `GET /api/evolution/receipts`、`POST /api/evolution/post-release/observe` 和 `GET /api/evolution/follow-up-actions`，第一版不新增后端接口。

页面分两个区域：回执选择与指标提交区、后续动作列表区。提交成功后在页面展示 `passed`、失败检查项、`rollback_suggestion` 和本次动作；后续动作列出 `pending` 高亮，并提供提案/回执/Artifact 跳转。第一版不提供 rollback/stop 执行入口，回滚继续使用 Artifact 管理页。

理由：文档将第一版定义为纯前端，避免与现有治理服务耦合；后端已有最小闭环能力。

替代方案：同时扩展后端返回更多指标来源。会扩大范围，推迟第一版上线。

### 9. 测试策略

- Claim 抽取：纯函数回归集覆盖中文/英文/混合标点、Markdown、表格、代码块、跨行股票代码/日期/金额/百分比/括号、`EPS/SH`、长报告和截断统计。
- LLM Judge：mock adapter 验证 `is_available`、默认模型解析、未支持模型 4xx、失败时 `NOT_CONFIGURED/ERROR`、`raw_output` 记录实际模型。
- Run：`create_run -> snapshot -> preflight -> trial -> runtime -> scorer -> metrics` 端到端，覆盖合法 snapshot、缺 `case_id`、历史 key 补回、真实 dataset 63 case、初始化失败不误填 trial 计数。
- Audit：状态映射、task/session/decision record 关联、空数据、partial、事件分页稳定性和权限边界。
- Bad Case 配置：默认值 seeding、发布即时生效、缓存失效、回滚、并发发布、关闭开关后不再新建但历史可见。
- Frontend：`vue-tsc --noEmit`，决策审计中文事件/分页/降级视图，发布后观测提交和后续动作列表组件测试。

## Risks / Trade-offs

- [Risk] Claim 合并规则可能误改事实 → **Mitigation**: 只对确定模式合并，不确定原文保留并标记低优先级或 `excluded_reason`。
- [Risk] 审计状态名变化会影响旧 client 和测试 → **Mitigation**: 保留 `legacy_unverified/unavailable` 映射，接口同时返回新状态和兼容字段。
- [Risk] Judge adapter 化可能让部分环境从“可用”变为 `NOT_CONFIGURED` → **Mitigation**: 保留 dashscope adapter，统一默认模型解析，所有失败路径输出明确原因。
- [Risk] 同步 preflight 会拒绝以前可以 fire-and-forget 的坏 snapshot → **Mitigation**: 这是目标行为；响应返回结构化 `preflight` 结果，创建流程不需要回滚已有运行。
- [Risk] 配置服务写入或缓存失效可能出现先读旧后读新 → **Mitigation**: 发布操作先落库成功后失效缓存，读取失败回退最近有效版本；关键路径记录版本。
- [Risk] 发布后观测页面只读，用户可能期待直接回滚 → **Mitigation**: 页面明确引导到 Artifact 管理，并只展示 `rollback_suggestion` 和关联链接。

## Migration Plan

1. 数据模型先新增可选字段和集合索引，不重写历史文档；旧数据缺失字段时保持可读。
2. Claim 抽取先作为 scorer 内部实现替换，同一版本输出兼容 `ClaimEvidence`，并在 `raw_output` 增加统计。
3. LLM Judge 先保留 dashscope adapter，再添加统一默认模型和 DeepSeek/OpenAI-compatible adapter；配置默认值迁移到统一解析器。
4. Run snapshot 先修复新增运行写入 `case_id`，再补历史快照兼容；preflight 先作为 start_run 的同步检查，再接入 `_execute_run` 兜底。
5. 决策审计先改后端状态和分页接口，再更新 `DecisionAudit.vue`；旧页面可以先消费兼容字段。
6. 线上 Bad Case 配置先由环境变量 seed 初始记录，再启用数据库发布版本；若配置服务异常，回退安全默认并关闭自动发现。
7. 发布后观测先只部署前端页面，后端接口保持不变；若页面出现回归，直接隐藏菜单即可回滚。

## Open Questions

- 是否需要把 `preflighting` 作为独立 Run status，还是继续用字段 `preflight` 表示。当前设计选择字段，避免改动前端状态字典。
- 20 条 Claim 上限是否需要变成 run 级可配置项。当前按文档默认 20 条实现，后续可在同一 pipeline 上增加配置参数。
