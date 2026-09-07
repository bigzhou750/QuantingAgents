## ADDED Requirements

### Requirement: Evaluation platform must preserve skill route and execution trace events

评测平台 MUST 在标准化 trace 中保存 `skill_route` 和 `skill_execute` 事件，并支持按 trial、run、Skill name 和 Skill version 查询。事件必须包含候选 Skill、选中 Skill、未选原因、加载结果、执行步骤和关联 tool call；缺失信息时 MUST 保留真实缺失标记。

#### Scenario: Record skill route decision
- **WHEN** Agent 在任务执行过程中调用 `load_skill` 或收到 Skill 路由结果
- **THEN** 系统保存包括候选 Skill、最终选择、选择理由或缺失原因的 `skill_route` 事件

#### Scenario: Record skill execution
- **WHEN** Skill 正文被加载并用于后续任务执行
- **THEN** 系统保存 `skill_execute` 事件，并可通过事件关联后续工具调用和最终输出

#### Scenario: Legacy trace has no skill event
- **WHEN** 旧 trial 中没有 `skill_route` 或 `skill_execute` 事件
- **THEN** 系统继续保留原 trace，并将 Skill 相关展示标记为不可用

### Requirement: Evaluation platform must support skill eval run variants and snapshots

评测运行 MUST 支持 Skill 评测变体配置，包括 `no_target_skill`、`skill_only` 和 `full_skill_set`，并 MUST 将目标 Skill、排除 Skill、Skill 集合快照、Skill 版本和运行时根目录写入 run snapshot。

#### Scenario: Create skill eval run
- **WHEN** 用户创建带 `skill_eval` 配置的评测运行
- **THEN** 运行快照保存 Skill 目标、变体、断言配置和相关版本信息

#### Scenario: Run snapshot keeps variants reproducible
- **WHEN** 后续按同一 run snapshot 重放
- **THEN** 系统使用相同 Skill 集合、变量配置和断言版本执行

### Requirement: Evaluation trial details must expose skill evaluation results

评测 trial 详情 MUST 展示 Skill 路由命中、执行断言、共存结果、无目标 Skill 基线对比和回归状态；新能力未启用或数据缺失时 MUST 显示显式不可用状态，不报错。

#### Scenario: Admin views skill eval trial
- **WHEN** 管理员打开包含 Skill 评测结果的 trial
- **THEN** 页面展示 route 结果、执行断言逐项结果和失败定位

#### Scenario: Skill eval not configured
- **WHEN** case 未配置 `skill_eval` 或运行未启用 Skill 评测
- **THEN** trial 详情对 Skill 区域显示 `not_configured`，其余评测内容保持正常
