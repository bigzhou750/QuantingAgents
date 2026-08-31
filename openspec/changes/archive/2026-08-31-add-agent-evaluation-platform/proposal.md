## Why

QuantingAgents 正在接入 Vibe Agent runtime，但目前缺少可复现、可对比、可回归的生产级 Agent 测评体系，无法稳定判断 Agent 的答案质量、工具过程、证据链、安全边界和运行成本。研发需要通过统一的 EvalOps 平台持续评估 Vibe Agent runtime 的版本变化，并将线上 bad case、trace 和人工复核沉淀为可治理的质量闭环。

## What Changes

- 新增面向 Vibe Agent runtime 的 Agent 测评平台，支持评测集、评测用例、批量运行、重复 trial、评分、人工复核和报告。
- 新增标准化 Agent trace 适配层，将 Vibe AgentLoop、LLM 调用、tool、skill、Swarm、memory、证据、错误和最终报告映射为可评分、可回放的统一事件。
- 新增分层评分体系，覆盖 outcome eval、trajectory eval、金融质量、证据质量、工具过程、安全治理和运行成本。
- 支持 LLM-as-judge 评分器，并通过固定 judge 模型、rubric、JSON schema、版本和人工复核进行治理。
- 支持规则评分、金融规则评分、证据评分、安全评分和人工复核，不把 LLM-as-judge 作为唯一裁判。
- 支持 pass@k、pass^k、方差、失败率、成本、延迟、token 和工具调用统计，用于区分能力上限和生产稳定性。
- 新增后台管理页面，用于研发/管理员管理评测集、发起评测运行、查看指标、回放 trace、复核分数和回流 bad case。
- 新增 bad case 池，将线上失败、用户反馈、安全拦截、人工复核样本转化为可版本化的评测用例。
- 支持与 Langfuse、Phoenix 等观测平台以及 DeepEval、Ragas、Promptfoo 等评测/红队工具的适配扩展，但核心评测编排和业务数据模型保留在 QuantingAgents 内部。
- 暂不将测评结果作为 CI 或发布门禁的强制阻断条件，但数据模型预留 release gate 和版本对比能力。
- 不修改现有单股分析、批量分析、报告和任务中心的行为契约；本变更仅测评新接入的 Vibe Agent runtime。

## Capabilities

### New Capabilities

- `agent-evaluation-platform`: 提供 Vibe Agent runtime 的评测集管理、批量运行、trace 标准化、分层评分、LLM-as-judge、人工复核、bad case 回流、评测报告和后台管理能力。

### Modified Capabilities

- 无。现有自然语言研究工作台、内置 Agent runtime、单股分析和批量分析的既有行为契约不变；本变更新增独立测评与治理能力。

## Impact

- **后端**：新增 Agent 测评服务、数据模型、API、runner、trace adapter、scorer hub、LLM judge、bad case service、report service 和安全评测扩展点。
- **前端**：新增后台管理页面，包括评测集、评测运行、运行详情、trial trace、评分复核、bad case 池和趋势报告。
- **数据存储**：MongoDB 保存评测集、case、run、trial、score、judge result、human review、bad case 和报告元数据；文件系统或对象存储保存大体量 trace、输入输出和证据快照引用。
- **运行环境**：复用 Vibe Agent runtime、QuantingAgents 任务/SSE/审计基础设施；可选接入 Langfuse/Phoenix 观测平台、DeepEval/Ragas 评分 SDK 和 Promptfoo 红队工具。
- **权限与审计**：后台测评功能仅允许研发/管理员角色访问；所有评测运行、LLM judge、人工复核和 bad case 回流必须记录操作者、配置版本、时间、输入输出引用和评分来源。
- **兼容性**：不改变现有单股分析、批量分析和普通自然语言研究工作台的用户路径；Agent 测评使用独立任务类型、路由、权限和运行目录。
- **验收标准**：研发/管理员能够在后台创建评测集���运行 Vibe Agent runtime 评测、查看每个 case 的多次 trial、trace、分层得分、失败原因和聚合报告，并能将失败样本回流为新评测用例。
