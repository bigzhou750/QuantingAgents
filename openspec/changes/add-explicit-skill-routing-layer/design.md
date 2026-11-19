## Context

当前 Skill 路由是隐式的：`SkillsLoader` 把全部 Skill 摘要注入系统 prompt，LLM 再通过 `load_skill` 自行选择。`add-skill-execution-evaluation-and-regression` 会先为 `skill_route`/`skill_execute` 建立可观测事件和评测断言，但不会改变“全量摘要 + 隐式选择”的架构。本 change 在已有事件契约之上加入显式路由层，仍然保留 `load_skill` 作为最终执行入口。

## Goals / Non-Goals

**Goals:**
- 建立可配置的路由策略版本和候选召回/重排流水线。
- 在主 Agent 上下文构建前缩小 Skill 候选空间。
- 复用并扩展 trace 中的 `skill_route` 事件，保留审计字段。
- 提供 fail-open/fail-closed 降级和路由指标。
- 保持未启用路由时的现有行为完全兼容。

**Non-Goals:**
- 不改变 Skill 文件格式、加载优先级、工具权限或模型 provider。
- 不实现 Skill 准入/沉淀流程。
- 不引入必须联网的专有路由服务，首期尽量复用现有模型 provider 和可配置 Embedding。
- 不让路由层替代 `load_skill` 的正文加载和执行语义。

## Decisions

### 1. 路由层作为 context 构建前的独立服务

新增 `SkillRouter` 服务，在 session 构建系统 prompt 之前接受任务输入，输出候选 Skill 列表。`SkillsLoader` 根据候选列表只注入候选摘要；Agent 仍调用 `load_skill` 加载正文。路由器返回的候选集写入 `skill_route` 事件，供第一个 change 中的 route scorer 消费。

**Alternative considered:** 在 `load_skill` 内做拦截式路由。该方案只影响加载时点，不能让系统 prompt 提前缩小候选空间，无法解决上下文稀释问题。

### 2. 路由策略采用可插拔阶段管道

路由策略分为三个阶段，每阶段可选启用：

```text
Stage 1: Rule recall
  按 Skill 路由索引中的触发边界、负向规则和工具依赖做第一轮过滤

Stage 2: Embedding recall
  对任务输入与 Skill name/description 做向量召回，取 TopK 候选

Stage 3: LLM rerank
  对阶段 1/2 的并集进行模型重排，输出最终有序候选
```

每个阶段输出候选来源、置信度、未选原因和耗时，策略版本保存所有阶段配置。首期允许只启用规则召回，Embedding 和 LLM rerank 按配置启用，避免引入额外依赖就阻塞落地。

### 3. 路由索引从 Skill 资产派生，Mongo 保存版本快照

路由索引数据包括 Skill name、description、触发边界、负向规则、工具依赖、类别、版本和 owner。基线从 SKILL.md frontmatter/可选 `routing.yaml` 派生，发布时写入 Mongo 作为不可变索引版本。内容原文仍以 Skill artifact 为准，索引只复制路由所需字段，避免出现第二份 Skill 事实源。

**Alternative considered:** 只从文件系统实时读取。该方案没有策略版本、灰度切换和指标历史，无法支撑路由评测。

### 4. 上下文注入采用“候选集优先，load_skill 最终执行”

`context.py` 获取 `RoutingResult` 后，只把 `candidate_skill_names` 的摘要交给 `SkillsLoader.get_descriptions` 过滤。若路由未启用或 fallback 到全量模式，则使用原逻辑。`load_skill` 不限制只能加载候选 Skill，但 trace 会记录“加载了不在候选集中的 Skill”，以便评测静默绕过和策略遗漏。

### 5. 降级采用任务风险分级

路由失败时读取低风险/高风险任务配置：低风险允许回退为全量摘要并标记 `routing_failed`；高风险暂停注入候选结果，保留原始输入和 trace，创建人工复核任务。风险分级复用现有 operation/policy 中的风险字段，不另造一套权限模型。

### 6. 路由评测复用 Skill 评测 case

显式路由评测直接复用 `add-skill-execution-evaluation-and-regression` 中的 expected_route case 和 route scorer。本 change 额外输出路由策略级指标：召回率、准确率、误触发率、漏触发率、静默绕过率、延迟和成本，并按策略版本和模型聚合。

### 7. 路由策略和部署版本化

每次策略保存为不可变版本，包含各阶段配置、TopK、embedding/rerank 模型和降级模式。管理员可发布、灰度、回滚，并通过评测 run 对比新旧策略；每次路由调用都写入使用的策略版本。

## Risks / Trade-offs

- [Risk] 路由阶段增多导致首 token 延迟上升 → Mitigation: 阶段默认只启用规则召回，Embedding/rerank 可配置 TopK 和超时，指标单独记录每阶段耗时。
- [Risk] Embedding 或 LLM rerank 把正确 Skill 排除 → Mitigation: 保留 fallback、静默绕过指标和人工复核队列，关键候选可由规则召回强制保留。
- [Risk] 路由索引与 Skill 内容漂移 → Mitigation: 每次 Skill 发布时重新派生索引版本，并校验 description/触发边界变更是否同时更新索引。
- [Risk] 与第一个 change 的事件契约出现分叉 → Mitigation: 本 change 只扩展 `skill_route` 字段，不新增第二套 route 事件类型。
- [Risk] 全量摘要回退可能恢复原有路由问题 → Mitigation: 低风险回退必须标记 `routing_failed`，并纳入路由失败率和人工抽查。

## Migration Plan

1. 新增路由索引模型、策略模型和 SkillRouter 服务，默认禁用。
2. 增加规则召回阶段，先从试点 Skill 生成路由索引。
3. 接入 `context.py`，启用路由时注入候选摘要，并为 `skill_route` 扩展策略字段。
4. 增加 Embedding/LLM rerank 可选阶段和超时配置。
5. 增加降级模式、路由指标和后台配置页面。
6. 使用第一个 change 的 Skill 评测集跑新旧策略对比。
7. 灰度启用前完成权限、审计、回滚和文档验证。

**Rollback:** 关闭 `SKILL_ROUTING_ENABLED` 后回到全量摘要加载；保留已写路由事件、策略版本和指标。回滚不禁用 Skill 评测事件，也不删除路由数据。

## Test Strategy

- 模型测试：路由索引、策略版本、TopK 和旧数据兼容。
- Router 测试：规则召回、Embedding 可选阶段、LLM rerank、空候选和超时。
- Context 测试：启用路由时只注入候选摘要，禁用时保持原行为。
- Trace 测试：策略版本、候选来源、未选原因和 fallback 标记。
- 降级测试：低风险回退、高风险暂停并生成人工复核。
- 评测测试：与第一个 change 的 route scorer 兼容，输出策略级指标。
- 前端测试：路由配置和指标页面的权限、旧 run 兼容和 type-check。
