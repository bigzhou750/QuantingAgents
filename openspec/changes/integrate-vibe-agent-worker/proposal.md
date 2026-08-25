## Why

QuantingAgents 现有的股票分析流程缺少完整的数据校验、证据链、ReAct 过程、工具调用轨迹和多智能体 Swarm 运行视图，生成的分析报告难以复核和建立信任。Vibe-Trading 已经具备自然语言金融研究 Agent、tools、skills、trace、SSE 会话和 Swarm 能力，但其文件型持久化缺少面向多用户系统所需的身份、权限和数据隔离。

本变更将 Vibe-Trading 的研究 Agent 能力以独立 Worker 模块接入 QuantingAgents，在保留 QuantingAgents 用户体系和任务中心的同时，提供隔离的自然语言研究工作台。

## What Changes

- 新增自然语言金融研究工作台入口，页面交互以 Vibe-Trading 的会话、SSE、工具轨迹和 Swarm 展示为基准。
- 引入独立的 Vibe Agent Worker 运行时，隔离现有 QuantingAgents 分析流程。
- 迁移 Vibe-Trading 的 Agent、ReAct、tools、skills、trace、Swarm 和相关研究产物能力。
- 通过 QuantingAgents API、Redis 命令/事件流和 Worker 适配层连接前端、任务中心与 Agent Worker。
- 将 QuantingAgents 登录用户映射为 Agent session、attempt、run 和产物的归属主体。
- 保留 Vibe-Trading 文件型 trace、session 和运行产物，但改为按用户和 session 隔离的运行目录。
- 将 Agent Worker 的 session、attempt、trace、Swarm run 和最终报告映射到 QuantingAgents 任务中心的新增任务类型。
- 允许迁移后的 tools、skills 和 Swarm 能力继续使用其既有功能；高风险工具调用必须纳入用户身份、权限和审计上下文。
- 保持现有 QuantingAgents 单股分析、批量分析、任务中心和报告接口的行为兼容，不重写既有分析链路。
- 增加 Worker 启停、任务恢复、SSE 断线重连、取消和失败处理机制。

## Capabilities

### New Capabilities

- `natural-language-research-workbench`: 提供登录用户可访问的自然语言金融研究页面、会话、消息、SSE 事件、工具轨迹、ReAct 过程、Swarm 状态和研究结果展示。
- `vibe-agent-worker-runtime`: 提供隔离的 Vibe Agent Worker 执行能力、任务协议、用户/session 作用域、文件型运行产物隔离、trace 持久化和任务生命周期管理。

### Modified Capabilities

- 无。现有 QuantingAgents 分析和任务能力保持行为兼容；本变更只增加新的 Agent 任务来源和页面入口。

## Impact

- **后端**：新增 Agent Worker 适配层、任务类型、Redis 命令/事件协议、用户作用域运行目录、SSE 代理接口和任务中心映射。
- **前端**：新增自然语言研究工作台路由和菜单入口；新增会话、流式输出、工具调用、trace、Swarm 和错误恢复展示。
- **数据存储**：MongoDB 保存用户可查询的任务/会话/运行元数据；文件系统保存按用户/session 隔离的 Vibe trace、上传文件和运行产物。
- **运行环境**：增加 Agent Worker 进程及 Vibe-Trading 依赖；需要复用现有 Redis，并定义 Worker 的启动、停止和健康检查方式。
- **安全与权限**：所有 Agent 请求必须经过 QuantingAgents 用户认证；文件写入、Shell、交易连接等高风险能力必须保留审计和权限上下文。
- **依赖与许可证**：迁移前需要核对 Vibe-Trading 代码、第三方依赖和许可证边界，不能将受限内容错误纳入 QuantingAgents 的分发范围。
