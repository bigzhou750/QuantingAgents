## Why

`docs/evaluation/claim-extraction-optimization.md` 记录了 2026-09-11 集中发现的评测可靠性和线上运营缺口：Claim 抽取仍按正则片段近似事实句，LLM Judge 默认模型与生产配置不一致，run snapshot 丢 `case_id` 会导致 0 Trial，决策审计页无法区分“无链”和“有运行事件但无结构化链”，线上 Bad Case 配置仍依赖环境变量，发布后质量观测没有前端页面。这些问题彼此都落在一个评测闭环上，单独修只解决局部，因此合并成一个 change 统一治理。

## What Changes

- 重构 Claim 抽取为 `归一化 -> 候选生成 -> 合并与完整性检查 -> Markdown/格式过滤 -> 排序 -> 数量上限 -> ClaimEvidence 构造` 的流水线，修复跨行数字、股票代码、日期、百分比、括号和英文缩写被切碎的问题。
- Claim 抽取输出排除统计和截断统计，记录 `claim_candidate_count`、`claim_count`、`claim_truncated`、`claim_truncated_count`、`claim_truncated_at` 和 `excluded_reason`；排除/截断内容不静默消失，也不进入证据覆盖率和幻觉指标分母。
- 保持 `ClaimEvidence`、`ScoreResult.claims`、Claim-Evidence 映射、URL/API 字段和现有评分接口兼容，仅扩展可选统计字段。
- 审计链展示从单一布尔状态扩展为 `complete`、`partial`、`events_without_chain`、`empty`，并返回 task/session 关联、各类数据数量、查询范围和结构化决策记录数。
- 为 `GET /api/decision-audit/chains/{identifier}/events` 增加后端分页，参数支持 `scope`、`page`、`page_size`，排序稳定，沿用现有权限和查询范围。
- 运行事件列表使用中文名称，兼容 `event_type=tool_call + payload.phase=tool_result`，未知事件保留原始名称。
- 新增线上 Bad Case 配置管理：环境变量只作为默认值，数据库配置作为运行时覆盖；支持当前配置、编辑发布、校验、历史、回滚、权限和审计。
- 新增统一 `OnlineBadcaseConfigService.get_effective_config()`，Collector/软评分器统一读取已校验快照，支持 TTL 缓存、发布主动失效和 fail-closed 回退。
- LLM Judge 改为复用统一 LLM 适配层，不再硬编码 `qwen-plus` 和 dashscope 依赖；默认模型来自唯一配置源，API 校验 `judge_model`，不可用时记录明确原因。
- 修复 run snapshot 契约：snapshot case value 保留 `case_id`，`_resolve_run_cases()` 兼容历史快照，缺少 `case_id` 时抛出结构化校验错误。
- 增加 run preflight、`failure_stage`、`error_code` 和结构化初始化结果，区分运行初始化失败、Trial 失败、评分失败和聚合失败；运行详情页首屏展示失败原因和 Trial 未创建状态。
- 新增自进化模块下的“发布后观测”独立页面：选择已发布回执、手工提交观测指标、查看结论和后续动作；第一版只读展示 rollback/bad_case/stop 候选，不做自动执行。
- 按文档补齐 Claim 抽取回归测试、审计关联/分页测试、Bad Case 配置边界测试、LLM Judge 模型回退测试、run snapshot 端到端测试和发布后观测页面测试。

**非目标**
- 不重写 Vibe Agent runtime 和普通投资分析主流程。
- 不把原始运行事件冒充为完整结构化决策链，也不自动执行回滚或 stop。
- 不改变线上 Bad Case 的硬失败、软信号、人工复核和回流语义，只改配置管理方式。
- 发布后观测第一版不自动拉取线上指标，也不在页面直接执行 rollback/stop。
- 不删除环境变量作为部署级默认值的能力，只降低它对运行时可调参数的依赖。

## Capabilities

### New Capabilities

- `decision-audit-chain-visibility`: 提供可区分的决策链状态、事件分页、原始事件降级视图和中文事件名称映射。
- `post-release-observation-ui`: 提供自进化模块下的发布后观测提交、结论展示和后续动作只读查看页面。

### Modified Capabilities

- `agent-evaluation-platform`: 增加高质量 Claim 抽取契约、LLM Judge 统一模型通道、run snapshot/preflight/失败阶段契约，并保持现有评分和数据结构兼容。
- `online-badcase-automation-and-reflow`: 增加系统级配置持久化、运行时生效快照、管理页、权限审计、历史回滚和 fail-closed 行为。

## Impact

- Backend: 涉及 `app/services/eval/scorers/evidence_scorer.py`、`app/services/eval/scorers/llm_judge_scorer.py`、`app/services/eval/scorer_hub.py`、`app/services/eval/runner_service.py`、`app/services/eval/online_badcase_service.py`、`app/services/explainability/audit_service.py`、`app/routers/decision_audit.py`、`app/routers/eval.py`、`app/models/eval.py` 和相关配置/自进化 API。
- Frontend: 涉及 `frontend/src/views/Evaluation/DecisionAudit.vue`、`frontend/src/views/VibeAgent/workbench.ts`、`frontend/src/api/evolutionClient.ts`、新增 `PostReleaseObservation.vue`、路由和侧边栏菜单。
- Data/API: 新增或扩展可选字段、索引、分页接口、配置版本记录和审计统计；新字段均可选，旧数据兼容。
- Permissions/UI: Bad Case 配置发布和回滚只允许自进化配置管理权限；普通复核人员只读；现有评测、审计和自进化管理员入口保持。
- Config/Compatibility: 保留现有环境变量作为默认值；LLM Judge 默认模型改为统一配置源；不改变现有 provider 依赖边界以外的外部系统。
- Testing: 覆盖 Claim 中文/英文/Markdown/跨行/截断样本，审计空数据/partial/关联/分页边界，Bad Case 配置回滚/并发/关闭开关，Judge 支持模型/未配置/fallback，run snapshot 合法/非法/历史兼容/真实数据集全链路，发布后观测页面类型检查和关键交互。
