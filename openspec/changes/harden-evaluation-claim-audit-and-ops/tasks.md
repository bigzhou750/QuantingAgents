## 1. Claim 抽取流水线
- [x] 1.1 新增 `app/services/eval/claim_extraction/` 目录和 `ClaimExtractionResult` 数据结构，实现 CRLF、Unicode 空白和连续空白归一化，并保留原文 span；通过新增 `tests/test_claim_extraction.py` 验证中文、英文、混合空白和 CRLF 输入
- [x] 1.2 实现候选片段生成，支持中英文句号、感叹号、问号和换行边界，并输出 `source_start/source_end`；验证即使原始文本带 Markdown 也不会在生成阶段先丢失定位信息
- [x] 1.3 实现确定性跨行合并，覆盖 `600519\nSH`、`65\n66 元`、被拆开的 `EPS/SH`、百分比、日期和括号内容；验证可确定模式被合并、不可确定数字保留原文并标记低优先级
- [x] 1.4 实现 Markdown 和格式过滤状态机，识别标题、fenced code block、表格表头/分隔线、引用块、水平分隔线和纯字段标签；验证这些内容被排除并记录 `excluded_reason`
- [x] 1.5 实现完整列表项保留，去掉 `-`/`*` 列表标记后作为 Claim 候选；验证 `- 2025 年净利润为 823 亿元。` 输出为不含列表标记的事实句
- [x] 1.6 实现 Claim 候选排序信号，给含数字/日期/股票代码/金额/百分比/完整谓词/完整句末标点的候选更高优先级；验证排序后事实句先于残缺片段
- [x] 1.7 在候选清理和排序之后应用默认 20 条上限，输出 `claim_candidate_count`、`claim_count`、`claim_truncated`、`claim_truncated_count`、`claim_truncated_at`；验证超过上限时统计正确
- [x] 1.8 将 `extract_claims()` 接入 `app/services/eval/scorers/evidence_scorer.py`，转换为现有 `ClaimEvidence` 并保持 `ScoreResult.claims`、Claim-Evidence 映射兼容；验证既有 evidence scorer 测试通过
- [x] 1.9 在 `raw_output` 中返回 Claim 统计和被排除原因；验证标题、格式行、残缺片段不进入 `evidence_coverage`、`unsupported_ratio`、`weakly_supported_ratio` 和幻觉指标分母
## 2. LLM Judge 统一模型通道
- [x] 2.1 新增 `app/services/eval/judge_adapters.py`，定义 `JudgeLLMClient` 协议和 adapter registry；验证 mock adapter 可注入 `LLMJudgeScorer`
- [x] 2.2 将现有 dashscope 调用封装为 `DashScopeJudgeClient`，行为与现状一致；验证 `_call_judge` 不再绕过 adapter 直接 import dashscope
- [x] 2.3 新增 DeepSeek 和 OpenAI-compatible adapter，复用 `tradingagents/llm_clients`；验证在 mock provider 下可完成调用并返回原始响应
- [x] 2.4 新增 `app/services/eval/judge_config.py` 作为默认 judge 模型唯一解析入口，读取 `EVAL_JUDGE_MODEL_DEFAULT` 或现有统一默认模型；验证 `scorer_hub` 和 `LLMJudgeScorer` 不再各自硬编码 `qwen-plus`
- [x] 2.5 修改 `LLMJudgeScorer.is_available`，改为检查受支持 adapter、凭据和模型集合；验证没有 dashscope 但有其他受支持 provider 时可用
- [x] 2.6 修改 `app/routers/eval.py` 和 `app/models/eval.py` 的 `judge_model` 校验，要求模型必须在受支持集合内；验证提交不支持模型返回明确 4xx 而不是静默 fallback
- [x] 2.7 在 `raw_output` 记录实际 `judge_model`、adapter 名称、调用耗时、成功/失败原因；验证评分失败时保留这些字段且返回 `NOT_CONFIGURED/ERROR`
- [x] 2.8 更新 `scorer_hub` 和 runner 实例化 Judge 的调用链，传入统一解析后的默认模型；验证 run 指定模型、未指定模型和测试 mock 三种路径都有测试覆盖
## 3. Run snapshot 契约与初始化失败
- [x] 3.1 修改 `app/services/eval/runner_service.py::create_run`，在每个 snapshot case value 中写入 `case_id`；通过新增测试验证持久化 snapshot 每个 value 都有 `case_id`
- [x] 3.2 修改 `_resolve_run_cases()`，优先使用 snapshot，并兼容历史快照从 dict key 补回 `case_id`；验证 value 缺 `case_id` 但 key 存在时可运行
- [x] 3.3 新增 `CaseSnapshotValidationError` 和 `RunFailureStage`/错误码枚举；验证 value 和 key 都缺 `case_id` 时返回结构化错误，不抛裸 `KeyError`
- [x] 3.4 在 `app/models/eval.py` 的 `EvalRun` 增加可选字段 `failure_stage`、`error_code`、`preflight`；验证旧 run 文档反序列化兼容
- [x] 3.5 新增 `_preflight_run()`，校验 snapshot 可解析、case 数量一致、`case_id` 唯一非空、`input.prompt`、dataset/snapshot 版本、scorer/judge 配置和超时；验证合法 snapshot 返回 `passed`
- [x] 3.6 在 `start_run()` 调度后台任务前同步执行 preflight；失败时置 Run 为 `failed`、写入结构化失败字段并返回 `started=false`；验证 API 响应包含 `preflight` 结果
- [x] 3.7 在 `_execute_run()` 开头调用同一 preflight 兜底；验证非法 snapshot 不会创建 Trial，`completed_trials=0`、`failed_trials=0`、`trial_count=0`
- [x] 3.8 更新 `app/routers/eval.py` 的 start API 返回 `started`、Run 状态和 preflight；验证旧调用方忽略新增字段仍兼容
- [x] 3.9 更新 `frontend/src/views/Evaluation/RunDetail.vue`，在状态摘要首屏展示运行状态、失败阶段、错误代码、错误原因和 Trial 未创建；验证 `vue-tsc --noEmit` 通过且页面组件测试覆盖初始化失败状态
## 4. 决策审计链可见性
- [x] 4.1 修改 `app/services/explainability/audit_service.py::build_audit`，返回 `complete`、`partial`、`events_without_chain`、`empty`；验证 `legacy_unverified` 映射为 `events_without_chain`、`unavailable` 映射为 `empty`
- [x] 4.2 在审计响应增加 `audit_counts`，至少包含 task/session ID、运行事件数、trace 数、决策记录数、解释/校验/复核数、查询范围；验证空数据和有数据状态数量正确
- [x] 4.3 新增 `GET /api/decision-audit/chains/{identifier}/events`，参数 `scope/page/page_size`，复用 task/session 解析和权限校验；验证返回 `items/page/page_size/total/has_more` 且排序稳定
- [x] 4.4 事件分页查询按 `sequence`/`created_at` 稳定排序，并设置上限保护；验证超过一页时 `has_more=true`、非法 `page_size` 被限制
- [x] 4.5 新增事件中文名称映射模块，同时识别 `event_type` 和 `payload.phase`；验证 `tool_call + phase=tool_result` 显示“工具返回”，未知事件保留原始名称
- [x] 4.6 更新 `app/routers/decision_audit.py` 注册事件分页接口并保持现有 `/chains/{identifier}` 路由兼容；验证无权限请求返回 403
- [x] 4.7 更新 `frontend/src/views/Evaluation/DecisionAudit.vue`，展示新状态、数据计数、分页表格、中文事件名称和 `events_without_chain` 降级提示；验证原始运行事件不被标注为完整决策链
- [x] 4.8 增加审计服务回归测试，覆盖 task/session/decision record 关联、空数据、partial、关联错误、分页边界和无权限；验证 `pytest tests/` 相关测试通过
## 5. 线上 Bad Case 配置管理
- [x] 5.1 在 `app/models/eval.py` 或新增配置模型中定义 `OnlineBadcaseConfig`，包含 `config_key`、`version`、`enabled`、`enable_judge`、`soft_sample_rate`、`confidence_threshold`、`judge_threshold`、`evidence_threshold`、`max_content_length`、`status`、`updated_by`、`updated_at`、`change_reason`；验证模型可序列化和旧字段兼容
- [x] 5.2 新增 `online_badcase_configs` 集合和索引，首次初始化从环境变量 seed 默认配置；验证初始化可重复执行且数据库不可用时回退安全默认值
- [x] 5.3 新增 `OnlineBadcaseConfigService`，提供 `get_effective_config`、`list_configs`、`create_draft`、`publish`、`rollback`；验证发布后不需要重启即可返回新配置
- [x] 5.4 实现配置校验规则：采样率和阈值范围 `0~1`、`max_content_length` 上限、开启 `enable_judge` 时检查 Judge 模型配置；验证非法配置不能发布
- [x] 5.5 实现短 TTL 缓存和发布主动失效；验证缓存命中、失效、数据库读取失败、无有效配置时 fail-closed 且默认关闭自动发现
- [x] 5.6 新增自进化配置管理 API，GET 只读、POST/发布/回滚要求自进化配置管理权限；验证越权返回 403
- [x] 5.7 修改 `app/services/eval/online_badcase_service.py`，让 `collect_soft_signals()`、`OnlineBadcaseAdjudicator` 和 Collector hook 统一读取 `get_effective_config()`；验证关闭总开关时不新建 Bad Case、历史数据仍可查看
- [x] 5.8 更新前端自进化管理页，新增“当前配置、编辑发布、历史回滚”三段视图并展示配置来源和生效状态；验证 `vue-tsc --noEmit` 和相关页面测试通过
- [x] 5.9 增加 Bad Case 配置测试，覆盖默认值、发布、回滚、缓存失效、并发发布、边界值、关闭开关和历史保留；验证 `pytest tests/` 相关测试通过
## 6. 发布后观测页面
- [x] 6.1 在 `frontend/src/api/evolutionClient.ts` 增加 `observePostRelease()`，复用现有 `getFollowUpActions()`；验证 API 方法可调用且不修改后端接口
- [x] 6.2 新增 `frontend/src/views/Evolution/PostReleaseObservation.vue`，加载已发布回执列表，选择 `receipt_id` 后填写 `success_rate`、`safety`、`evidence_quality`、`latency mean_ms`、`cost total_usd`；验证表单提交走 `POST /api/evolution/post-release/observe`
- [x] 6.3 提交后展示 `passed`、失败检查项、`rollback_suggestion` 和本次生成的后续动作；验证失败指标能触发回滚建议展示
- [x] 6.4 页面展示后续动作列表字段并高亮 `pending`，提供提案、回执和 Artifact 跳转；验证第一版没有 rollback/stop 执行入口
- [x] 6.5 在 `frontend/src/router/index.ts` 和侧边栏菜单增加 `/evolution/observation`“发布后观测”入口；验证管理员可访问、无权限用户不可访问
- [x] 6.6 增加页面组件测试，覆盖回执加载、指标提交成功、指标提交失败、后续动作加载和 pending 高亮；验证 `vue-tsc --noEmit` 和组件测试通过
## 7. 集成验证
- [x] 7.1 运行 Claim 抽取、LLM Judge、runner snapshot、决策审计、Bad Case 配置相关 `pytest` 测试；验证新增与既有评测测试全部通过
- [x] 7.2 增加从真实 dataset 到 run snapshot、preflight、Trial、scorer、metrics 的端到端测试；验证 63 Case 固定数据集不会出现 `total_cases=63` 但 Trial 为 0
- [x] 7.3 增加 1 Case 端到端启动测试和非法 snapshot 测试；验证合法 snapshot 创建 Trial，非法 snapshot 返回结构化初始化失败
- [x] 7.4 运行前端 `vue-tsc --noEmit` 和决策审计/发布后观测相关测试；验证前端类型和关键交互无回归
- [x] 7.5 运行 `openspec validate --change harden-evaluation-claim-audit-and-ops --strict`；验证所有 planning artifacts 通过
- [x] 7.6 修复决策审计事件分页页码未更新和 `token` 事件污染问题；验证后端分页条件排除 `event_type=token`、页码 offset 正确，前端 `vue-tsc --noEmit` 与审计相关测试通过
- [x] 7.7 增加前端 token 事件兜底过滤并重建 `frontend/dist`；验证生产 bundle 已包含最新决策审计分页与过滤逻辑
