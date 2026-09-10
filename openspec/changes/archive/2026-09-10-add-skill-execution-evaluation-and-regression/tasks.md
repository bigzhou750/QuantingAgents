## 1. 数据模型与运行快照

- [x] 1.1 在 `app/models/eval.py` 的 `EvalCase`/`scoring_criteria` 中新增可选 `skill_eval` 结构，覆盖 expected_route、execution_asserts、coexistence、baseline_variant 和 critical，并用旧 case fixture 验证缺失字段时模型可读（spec: Skill evaluation cases must declare expected route behavior; design: 1, 9）
- [x] 1.2 扩展 `EvalRunConfig`，增加 `skill_eval.variant`、`skill_scope`、`skill_versions` 和 `regression_refs`，并用快照测试验证 run 创建时固化 Skill 集合与版本（spec: Evaluation platform must support skill eval run variants and snapshots; design: 2, 7）
- [x] 1.3 新增 `SkillRegressionGroup` 模型和 Mongo 索引，保存 baseline/candidate run、dataset/version、Skill 版本、model、scorer 版本、critical_cases 和 gate 结果，并通过 CRUD 测试验证（spec: Skill regression must compare paired versions per case; design: 7）

## 2. Runtime Route/Execute 事件

- [x] 2.1 在 `vibe_agent_runtime/vendor/src/agent/skills.py` 和 `context.py` 中 emit `skill_route` 事件，记录候选 Skill、选中/未选 Skill 和 `candidates_unavailable`，用 trace 测试验证事件顺序和字段（spec: Evaluation platform must preserve skill route and execution trace events; design: 3）
- [x] 2.2 在 `vibe_agent_runtime/vendor/src/tools/load_skill_tool.py` 中 emit `skill_execute` 事件，记录加载结果、读取位置和关联 tool call，并用 runtime fixture 验证事件可回放（spec: Evaluation platform must preserve skill route and execution trace events; design: 3）
- [x] 2.3 扩展 `app/services/eval/trace_adapter.py`，把 runtime 新事件完整映射到 `skill_route`/`skill_execute`，并增加 `route_selected`/`skill_effective` 标记字段，用 adapter 测试验证旧事件不回归（spec: Evaluation platform must preserve skill route and execution trace events; design: 4）

## 3. Skill 专用评分器

- [x] 3.1 新增 `skill_route_scorer`，基于 expected_route 与 route 事件计算命中、误触发、漏触发和静默绕过，用正/负/边界样本测试验证（spec: Skill evaluation cases must declare expected route behavior; design: 4）
- [x] 3.2 新增 `skill_execution_scorer`，程序断言 required_tools、forbidden_tools、required_files、schema、formula 和 state_checks，用确定性 fixture 验证文件/schema/状态断言结果（spec: Skill evaluation cases must declare deterministic execution assertions; design: 5）
- [x] 3.3 新增 `skill_coexistence_scorer`，比较目标 Skill 与相邻 Skill 的成功率、触发分布和共享状态影响，用冲突对 fixture 验证抢触发和拖累邻居被识别（spec: Skill coexistence evaluation must detect conflicts; design: 6）
- [x] 3.4 在 `app/services/eval/scorer_hub.py` 注册三个新 scorer，并用 list/score 测试验证可用状态和 `not_configured` 语义（spec: Skill evaluation results must be auditable and version-pinned; design: 9）

## 4. Runner 变体与基线

- [x] 4.1 为 `SkillsLoader` 增加 `no_target_skill` 过滤能力，只排除目标 Skill，并用单元测试验证其余 Skill、工具和系统 prompt 不变（spec: Skill evaluation runner must support isolation variants and baselines; design: 2）
- [x] 4.2 在 `app/services/eval/runner_service.py` 支持 `no_target_skill`、`skill_only`、`full_skill_set` 三种变体，并用集成测试验证变体快照和 run 结果隔离（spec: Skill evaluation runner must support isolation variants and baselines; design: 2）
- [x] 4.3 为 `tushare`、`eastmoney`、`okx-market`、`yfinance`、`ccxt` 首期试点编写 Golden Case 数据集，包含正/负/边界路由样本和确定性执行断言，并验证可导入版本化数据集（spec: Skill evaluation cases must declare expected route behavior; design: 6）

## 5. 配对回归与发布门禁

- [x] 5.1 新增配对回归服务，支持创建 `baseline_run_id`/`candidate_run_id` 对和逐 case 对比，并用同一 dataset_version 的 fixture 验证结果可复现（spec: Skill regression must compare paired versions per case; design: 7）
- [x] 5.2 实现逐 case delta 聚合，输出路由、执行、共存、最终输出、成本、延迟和失败样本，并用测试验证分子分母和空样本处理（spec: Skill regression must compare paired versions per case; design: 7）
- [x] 5.3 实现 critical 回归门禁，critical case 回退、安全失败或确定性断言失败返回 block，并用测试验证平均分提升不能绕过（spec: Critical Skill regression must block promotion; design: 7）
- [x] 5.4 新增回归组查询和对比 API，校验评测权限并兼容旧 run，用 API 测试验证越权拒绝和旧数据响应（spec: Skill regression must compare paired versions per case; design: 7, 9）

## 6. 自进化集成

- [x] 6.1 修改 `app/services/evolution/verification_service.py`，候选 Skill 验证时创建/复用配对回归组，并让 `new_regressions` 返回逐 case delta，用验证集成测试覆盖（spec: Critical Skill regression must block promotion; design: 8）
- [x] 6.2 修改 `app/services/evolution/promote_service.py`，Skill promote 前必须通过配对回归 gate，critical 回退时拒绝发布并写入 receipt 和 Bad Case 引用，用 promote 测试验证（spec: Critical Skill regression must block promotion; design: 8）
- [x] 6.3 为缺失回归结果但允许管理员覆盖的场景增加显式配置和审计字段，用配置测试验证默认拒绝、覆盖后留痕（spec: Skill evaluation results must be auditable and version-pinned; design: 8）

## 7. API 与前端展示

- [x] 7.1 在评测 trial 详情 API 和页面中展示 route_selected、skill_effective、执行断言、共存结果和回归状态，旧 trial 显示 `legacy_unverified`，用 type-check 和组件测试验证（spec: Evaluation trial details must expose skill evaluation results; design: 9）
- [x] 7.2 在 run 报告页增加 Skill 维度摘要和逐 case 回归对比入口，并用前端类型检查和组件测试验证（spec: Evaluation trial details must expose skill evaluation results; design: 7）

## 8. 验证与文档

- [x] 8.1 运行模型、trace、scorer、runner、回归、evolution 相关 pytest，并执行 `openspec validate add-skill-execution-evaluation-and-regression --strict`（spec: 全部; design: Test Strategy）
- [x] 8.2 运行 `npm run type-check` 和相关前端组件测试，验证旧 trial 和未启用 Skill 评测页面不报错（spec: Evaluation trial details must expose skill evaluation results; design: Test Strategy）
- [x] 8.3 更新评测和自进化文档，说明 skill_eval 配置、变体口径、回归门禁和 promote 阻断规则，通过文档审查确认与 proposal/spec/design 一致（spec: 全部; design: Migration Plan）
