## Purpose

为 Skill 提供可证明的能力评测与版本回归机制，覆盖路由是否准确、独立执行是否满足确定性断言、共存是否冲突以及新版本是否相对旧版本回退，使 Skill 发布和自进化 promote 可以被真实证据约束。

## ADDED Requirements

### Requirement: Skill evaluation cases must declare expected route behavior

Skill 评测 case MUST 声明目标 Skill 的正向触发条件、负向不触发条件和边界样本，并 MUST 将“调用了 `load_skill`”与“Skill 内容对后续执行产生了影响”分开记录。当路由信息缺失时 MUST 标记为 `route_unavailable`，不得伪造触发结果。

#### Scenario: Positive route sample
- **WHEN** 评测 case 明确要求触发 `tushare` 且运行时发出了针对 `tushare` 的 `skill_route` 事件
- **THEN** 系统将路由判定为命中并记录为触发成功

#### Scenario: Negative route sample
- **WHEN** 评测 case 明确禁止触发 `eastmoney` 但 Agent 仍然调用 `load_skill("eastmoney")`
- **THEN** 系统将路由判定为误触发并生成失败原因

#### Scenario: Silent bypass
- **WHEN** Skill 摘要已注入上下文或 Skill 对任务应产生作用，但执行全程没有任何 `skill_route` 或 `skill_execute` 事件
- **THEN** 系统将采样标记为静默绕过并降低路由评分

### Requirement: Skill evaluation cases must declare deterministic execution assertions

Skill 评测 case MUST 支持声明必需工具、禁止工具、必需文件、schema、公式、环境状态变更和可观察验收点，并使用程序断言计算执行结果。无法从 trace 或产物取得断言输入时 MUST 返回 `unscorable` 或 `not_configured`。

#### Scenario: Required tool call is missing
- **WHEN** case 声明必须调用 `tushare_daily` 但 trace 中没有该工具调用
- **THEN** 执行断言失败并记录缺失步骤

#### Scenario: Output file and schema are checked
- **WHEN** case 要求生成指定 CSV 文件且字段符合 schema
- **THEN** 系统通过程序检查文件存在性、字段名和关键数据格式并返回确定性分数

#### Scenario: Environment state change is verified
- **WHEN** Skill 应写入数据库或修改外部状态
- **THEN** 系统必须基于前后状态记录判断变更是否发生且符合预期

### Requirement: Skill evaluation runner must support isolation variants and baselines

评测运行 MUST 支持在相同输入、模型、工具集合和系统 prompt 下执行至少三种变体：无目标 Skill 基线、目标 Skill 独立执行和真实 Skill 集合共存执行。每种变体 MUST 记录所使用的 Skill 集合、Skill 版本、模型版本、工具集合和运行时根目录。

#### Scenario: No-target-skill baseline
- **WHEN** 运行配置指定 `no_target_skill` 变体
- **THEN** 系统只从可用 Skill 集合中排除目标 Skill，其余 Skill、工具和系统 prompt 保持一致

#### Scenario: Isolated target skill execution
- **WHEN** 运行配置指定 `skill_only` 变体
- **THEN** 系统在受控 Skill 集合中只暴露目标 Skill 并记录独立执行结果

#### Scenario: Full skill set coexistence
- **WHEN** 运行配置指定 `full_skill_set` 变体
- **THEN** 系统使用真实 Skill 集合执行，并为共存冲突评分保留完整 trace

### Requirement: Skill coexistence evaluation must detect conflicts

系统 MUST 支持将目标 Skill 放入真实 Skill 集合，并检测描述相近、工具重叠、任务抢触发、错误组合、任务转交错误和共享状态被破坏等冲突。冲突测试集 MUST 支持人工挑选的优先级对，首期不要求全量两两组合。

#### Scenario: Similar skill steals a task
- **WHEN** 请求本应触发目标 Skill，但相似 Skill 被选中并执行
- **THEN** 共存评分记录抢触发，并生成目标 Skill 触发失败

#### Scenario: Neighbor skill success rate drops
- **WHEN** 目标 Skill 加入集合后，其他 Skill 在同一回归集中的成功率下降
- **THEN** 系统将下降记录为目标 Skill 的共存负影响

### Requirement: Skill regression must compare paired versions per case

系统 MUST 支持将同一数据集版本、同一模型和同一 Skill 断言下的旧版 run 与新版 run 配对比较，并 MUST 输出逐 case、逐评分维度的 delta、关键场景标记和失败样本列表。

#### Scenario: Paired baseline and candidate run
- **WHEN** 用户指定 `baseline_run_id`、`candidate_run_id` 和共享 `dataset_version`
- **THEN** 系统逐 case 比较 Skill 路由、执行、共存和最终输出结果

#### Scenario: Case-level regression delta
- **WHEN** 某个 case 的候选版本分数低于基线版本
- **THEN** 系统记录该 case 的回退 delta、失败评分维度和相关 trace 引用

### Requirement: Critical Skill regression must block promotion

Skill 发布或自进化 promote MUST 在 critical case 出现回退、安全断言失败或确定性执行断言失败时被阻止，即使总体平均分提升。回归结果 MUST 明确列出阻断 case 和原因。

#### Scenario: Critical case regresses
- **WHEN** 候选 Skill 在 `critical: true` 的 case 中触发或执行失败
- **THEN** release gate 返回失败并禁止 promote

#### Scenario: Aggregate score improves but critical case fails
- **WHEN** 候选版本总体平均分高于基线但存在 critical 回退
- **THEN** 系统仍将门禁判定为失败

### Requirement: Skill evaluation results must be auditable and version-pinned

Skill 评测结果 MUST 保存 input、expected_route、actual route 事件、执行断言、共存结果、最终输出、Scorer 版本、模型版本、Skill 版本、Skill 集合和运行时环境；缺少任一关键版本信息时 MUST 标记为 `unverifiable` 并不得参与有效指标分母。

#### Scenario: Complete audit record
- **WHEN** Skill 评测完成
- **THEN** 系统保存完整可追溯记录，并允许按 trial、run、Skill 版本或 case 查询

#### Scenario: Missing skill version
- **WHEN** trace 或运行快照无法提供目标 Skill 版本
- **THEN** 相关性指标标记为 `unverifiable`，避免误报有效结论

### Requirement: Skill evaluation compatibility must preserve legacy data

新增 Skill 评测字段 MUST 全部可选；旧评测 trial、旧 trace 和旧 run 缺少 Skill 断言时 MUST 继续可读，并显示 `legacy_unverified` 或 `not_configured`，不得影响既有评分语义。

#### Scenario: Legacy trial remains readable
- **WHEN** 用户查看 Skill 评测能力上线前创建的 trial
- **THEN** 原 trace、分值和复核记录保持可读，Skill 维度显示不可用状态

#### Scenario: Scorer lacks skill data
- **WHEN** 评分器因缺少 route/execute 事件或断言配置无法评分
- **THEN** 评分结果必须标记为 `skipped`、`not_configured` 或 `unscorable`
