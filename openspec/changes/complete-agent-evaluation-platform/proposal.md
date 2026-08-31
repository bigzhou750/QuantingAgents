## Why

当前 Agent 评测平台已经具备基础数据集、运行、评分、复核和 bad case 能力，但交互仍偏 MVP：管理员很难从一次评测直接看到最终输出、证据链、聚合指标、报告、趋势下钻和闭环动作。需要补齐生产级评测工作台，让评测从“能跑”升级为“能分析、能复核、能回流、能门禁”。

## What Changes

- 补齐数据集管理交互：Case 编辑、删除、批量导入、批量编辑、版本发布、空数据引导和内置 Golden Set 导入。
- 补齐运行详情：展示 Final Output、输入、错误、token/成本、评分摘要、`pass@k`、`pass^k`、trace 和人工复核状态。
- 新增运行报告页：承载后端 report 数据，支持留档、分享和导出。
- 增强评分和复核：支持评分器选择、judge 配置、未启用 scorer 的 skipped/not_configured 状态、复核上下文和复核后回流。
- 升级 evidence/grounding：从粗粒度证据质量分，升级为 claim -> evidence 的逐条可审计结构。
- 增强趋势和对比：增加图例、口径说明、pass@k/pass^k 趋势、run 对比、失败聚类下钻和结果钻取。
- 补齐生产治理：release gate、定时回归、线上抽样、数据快照、成本预算、告警订阅和第三方观测配置入口。
- 不改变普通用户的投资分析主流程；评测平台仍由管理员/研发角色使用。

## Capabilities

### New Capabilities
- `agent-evaluation-production-workbench`: 覆盖生产级 Agent 评测工作台的数据集、运行详情、报告、复核、证据链、趋势、对比、门禁和治理能力。

### Modified Capabilities
- 无。

## Impact

- Backend: `app/routers/eval.py`、`app/services/eval/*`、`app/models/eval.py`、评测数据导入和报告/门禁相关服务。
- Frontend: `frontend/src/views/Evaluation/*`、`frontend/src/api/evalClient.ts`、路由和管理员菜单。
- Data: MongoDB 中 eval datasets、cases、runs、trials、scores、bad cases、trace events 需要补充版本、快照、证据链、审批和导出字段。
- Config: 继续沿用 `EVAL_PLATFORM_ENABLED` / `VITE_EVAL_PLATFORM_ENABLED`，新增可选 scorer、judge、gate、scheduler 和 observability 配置。
- Tests: 需要覆盖 API、评分聚合、claim-evidence、权限、UI typecheck 和关键页面交互。
