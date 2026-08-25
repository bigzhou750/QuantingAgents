## Why

QuantingAgents 需要提供 Vibe-Trading 的完整自然语言金融研究 Agent 能力，而不是只把请求转发到一个外部源码目录。当前桥接方案没有把 AgentLoop、tools、skills、Swarm、trace 和会话运行时真正纳入本项目，导致能力边界不清晰、部署依赖本地绝对路径，且难以统一用户隔离、权限和任务生命周期。

本变更将 Vibe Agent runtime 的必要代码整体迁入 QuantingAgents，由 QuantingAgents 前端输入框直接进入本项目内的 Agent 会话和执行链路，同时保留现有认证、用户隔离、SSE、任务中心和审计体系。

## What Changes

- 将 Vibe Agent runtime 的必要源码迁入 QuantingAgents 内部受控目录，不再运行时依赖 `/Users/.../Vibe-Trading` 等外部绝对路径。
- 迁入并接通 AgentLoop、session/service/store/events、trace、checkpoint、memory、provider/config 适配层。
- 迁入 Vibe 的 tools、tool registry、skills、SkillsLoader、Swarm runtime、Swarm store、preset 和相关执行能力。
- 将自然语言研究工作台的输入框、会话、消息、SSE 和 AgentLoop 连接为一条本地运行链路。
- 通过 QuantingAgents 用户身份、权限和 session 上下文约束 tools、skills、Swarm 及文件型产物。
- 将 Vibe 的文件型运行数据重定向到 QuantingAgents 管理的运行目录，并按用户/session 隔离。
- 将 Agent 事件、工具调用、证据、ReAct 摘要、Swarm 状态和最终报告统一映射到现有 API 与任务中心。
- 保留 Agent runtime 与现有单股分析、批量分析执行链路的边界，避免改变既有分析行为。
- 增加迁移清单、许可证边界、依赖兼容、能力发现、失败恢复、取消、SSE 重连和回归测试。
- 移除当前仅用于加载外部 Vibe 源码的 child-process/source-root 依赖；Worker 如保留，仅作为 QuantingAgents 内部 runtime 的隔离执行入口。

## Capabilities

### New Capabilities

- `embedded-vibe-agent-runtime`: 描述迁入 QuantingAgents 的 AgentLoop、会话、tools、skills、Swarm、trace、memory 和本地运行时能力。
- `natural-language-research-workbench`: 描述前端输入框、会话交互、SSE 事件、工具轨迹、证据、ReAct、Swarm 和研究结果展示。
- `vibe-agent-isolation-and-governance`: 描述用户身份、权限、文件隔离、审计、任务生命周期和现有分析链路隔离。

### Modified Capabilities

- 无。现有股票分析能力的行为契约不变；本变更新增内置 Agent 能力及其工作台。

## Impact

- **源码结构**：新增 QuantingAgents 内部 Agent runtime 包、迁移的 tools/skills/Swarm 模块和适配层。
- **后端**：修改自然语言研究 API、SSE、任务中心、权限和审计接入；移除对外部 Vibe source root 的运行时依赖。
- **前端**：研究工作台继续作为独立入口，但数据源改为本地内置 Agent runtime 的事件和结果。
- **依赖**：需要核对 Vibe runtime 的 Python 依赖、QuantingAgents 现有依赖冲突、第三方许可证和分发边界。
- **数据存储**：MongoDB 保存用户、session、task、event 元数据；文件系统保存按用户/session 隔离的 trace、Swarm run、上传文件和报告产物。
- **兼容性**：现有认证、单股分析、批量分析、报告和任务中心接口必须保持兼容；Agent 任务使用独立任务类型。
