## Why

当前 Skill 的选择完全由 LLM 在系统 prompt 中看到全部 Skill 摘要后隐式完成。随着 Skill 数量增长，候选空间过大会导致误触发、漏触发、上下文稀释和路由成本不可控；评测只能记录隐式选择，无法在进入主 Agent 前缩小候选空间。需要补一个显式路由层，把“该不该考虑某个 Skill、最终加载哪个 Skill”变成可配置、可观测、可评测的系统能力。

## What Changes

- 新增 Skill 路由索引和路由元数据模型，保存 Skill 名称、描述、触发边界、负向规则、工具依赖、类别、版本、owner 和路由状态。
- 新增 `SkillRouter` 服务，支持规则召回、Embedding 召回和 LLM 重排的组合策略，并输出 TopK 候选 Skill。
- 在主 Agent 上下文构建前执行路由，只向系统 prompt 注入候选 Skill 摘要，保留 `load_skill` 作为最终加载入口。
- 扩展 `skill_route` 事件，记录路由策略版本、候选 Skill、最终选中、未选原因、路由耗时和 fallback 原因。
- 为路由策略提供 fail-open/fail-closed 降级：路由模块异常时低风险任务回退为全量摘要，高风险任务阻断或要求人工复核。
- 新增路由评测指标：召回率、准确率、误触发率、漏触发率、静默绕过率、路由延迟和路由成本。
- 在评测后台增加路由配置和路由命中分析入口，支持正样本、负样本、边界样本和模型差异对比。

## Capabilities

### New Capabilities
- `skill-routing-layer`: 覆盖 Skill 索引、候选召回、TopK 重排、路由事件、降级策略和路由指标。

### Modified Capabilities
- `agent-evaluation-platform`: 在评测平台中增加路由策略、路由指标和路由命中的可观测展示，使路由准确性可回归。

## Impact

- **Backend**: 新增 `app/services/skill_routing/` 路由索引、召回、重排、降级和指标服务，扩展 `app/models/` 与 `app/routers/`。
- **Runtime**: 修改 `vibe_agent_runtime/vendor/src/agent/context.py` 和 `session/service.py`，接入路由候选集注入。
- **Data**: 新增 Skill 路由索引集合、路由策略版本、路由事件字段和路由指标集合；现有 Skill 文件和 `eval_trace_events` 保持兼容。
- **Frontend**: 在评测后台增加路由配置、策略版本、候选命中分析和指标页面。
- **Config**: 新增路由策略、TopK、embedding 模型、fallback 模式和风险分级配置，默认关闭或按策略启用。
- **Permissions**: 路由配置仅管理员可写；普通用户只能看到最终注入的 Skill 结果，不暴露路由内部原始 reasoning。
- **Compatibility**: 未启用显式路由时保留现有全量摘要 + `load_skill` 行为，已写 trace 保持可读。

## 非目标

- 不改变 Skill 文件格式、加载优先级或工具权限边界。
- 不实现“什么经验值得沉淀成 Skill”的准入流程。
- 不把路由重排的原始模型 reasoning 暴露给普通用户。
- 不承诺 Embedding 或重排模型选型，首期支持可配置适配器。
