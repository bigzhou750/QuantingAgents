## Why

现有评测平台无法证明 Skill 的增量价值：`skill_route`/`skill_execute` 只有 trace 类型，运行时没有真正发出这两个事件；评测 case 缺少“应不应该触发、是否执行了正确步骤、是否影响其他 Skill”的断言；发布门禁只看聚合指标，关键场景回退不会阻止 Skill 上线。需要补上 Skill 专用评测与配对回归能力，使 Skill 有效性可证明、版本回退可阻断。

## What Changes

- 扩展 `EvalCase` 的 `scoring_criteria`，新增可选 `skill_eval` 配置块，覆盖路由断言、执行断言、共存配置、无目标 Skill 基线和关键场景标记。
- 在 Vibe runtime 的 skill 注入和 `load_skill` 调用链中发出 `skill_route`/`skill_execute` 事件，记录候选 Skill、最终选择、未选原因、加载结果和执行状态。
- 新增 `skill_route_scorer`、`skill_execution_scorer` 和 `skill_coexistence_scorer`，将路由准确性、确定性执行结果和共存冲突纳入评分体系。
- 使用 `no_target_skill` 作为默认增量价值基线：只禁用目标 Skill，其他 Skill、工具和系统 prompt 保持不变。
- 为 Skill 评测提供三种运行变体：无目标 Skill 基线、目标 Skill 独立执行、真实 Skill 集合共存执行。
- 将回归从聚合指标对比升级为配对 run 对比，支持逐 case 指标、关键场景回退和 critical 场景阻断。
- 将 Skill 回归结果接入自进化 verify/promote 门禁，使 `new_regressions` 可具体到 case 和评分维度。
- 在评测 trial 详情中展示 Skill 触发、执行断言、共存结果和回归对比，旧数据缺失新字段时保持兼容显示。

## Capabilities

### New Capabilities
- `skill-execution-evaluation-and-regression`: 覆盖 Skill 路由断言、独立执行断言、共存冲突、无目标 Skill 基线和配对回归门禁。

### Modified Capabilities
- `agent-evaluation-platform`: 扩展 trace 事件契约、run snapshot 和 trial 详情，使现有评测平台能消费和执行 Skill 专用评测与回归结果。

## Impact

- **Backend**: 修改 `app/models/eval.py`、`app/services/eval/dataset_service.py`、`app/services/eval/runner_service.py`、`app/services/eval/trace_adapter.py` 和 `app/services/eval/metrics_service.py`，新增 Skill 评测 scorer。
- **Runtime**: 修改 `vibe_agent_runtime/vendor/src/agent/skills.py`、`context.py` 和 `tools/load_skill_tool.py`，补充 route/execute 事件。
- **Evolution**: 修改 `app/services/evolution/verification_service.py` 和 `promote_service.py`，消费配对回归结果并阻止关键场景回退。
- **Frontend**: 在评测 trial 详情和 run 报告中增加 Skill 维度、断言结果和回归对比展示。
- **Data**: `eval_cases`、`eval_runs`、`eval_trace_events`、`eval_scores` 和回归对比结果需要兼容新增字段；历史数据缺少 Skill 字段时标记 `not_configured` 或 `legacy_unverified`。
- **Config/API**: 不改变现有普通用户 API；评测 API 新增 Skill 评测配置和配对回归接口。
- **Compatibility**: 普通评测、第三方 scorer 和旧 trial 展示保持兼容；新 Skill 字段全部可选。

## 非目标

- 不实现显式 Skill 路由模块或策略层，只建立可观测的 route 事件和路由断言契约。
- 不实现“什么经验值得沉淀成 Skill”的准入流程，该能力应作为独立 change。
- 不改变 Skill 文件格式、加载优先级或现有工具权限边界。
