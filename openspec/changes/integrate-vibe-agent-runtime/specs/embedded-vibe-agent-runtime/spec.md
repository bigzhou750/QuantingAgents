## Purpose

为 QuantingAgents 提供完整、可部署且不依赖外部源码路径的自然语言 Agent runtime，使用户输入能够进入迁入项目内部的 AgentLoop，并继续使用 Vibe 的工具、技能、Swarm、trace 和恢复能力。

## ADDED Requirements

### Requirement: Agent runtime must be packaged inside QuantingAgents

系统 MUST 将 AgentLoop、会话生命周期、工具注册、技能加载、Swarm 执行、trace、memory 和运行时配置的必要代码作为 QuantingAgents 内部模块交付。运行时 MUST NOT 依赖开发者机器上的外部 Vibe-Trading 源码绝对路径。

#### Scenario: Clean deployment starts the Agent runtime
- **WHEN** QuantingAgents 被部署到一台没有 Vibe-Trading 源码目录的机器
- **THEN** Agent runtime 仍能启动并处理研究任务

#### Scenario: Runtime source inventory is complete
- **WHEN** 构建或启动 Agent runtime
- **THEN** 系统能加载迁入范围内的 AgentLoop、session、tools、skills、Swarm、trace、memory 和必要 provider/config 模块，并报告不可用模块及原因

### Requirement: Natural-language input must execute through the migrated AgentLoop

系统 MUST 将已认证用户提交的研究消息转换为内部 Agent session 和 execution attempt，并由迁入的 AgentLoop 执行，而不是调用外部 Vibe HTTP API 或外部源码进程。

#### Scenario: Submit a research message
- **WHEN** 用户在研究工作台提交自然语言问题
- **THEN** 系统创建归属该用户的 session/attempt，执行 AgentLoop，并返回可关联的 task 标识

#### Scenario: Agent runtime failure
- **WHEN** AgentLoop、provider 或工具注册失败
- **THEN** 系统保存失败状态、诊断信息和可重连的事件，不影响现有股票分析链路

### Requirement: Migrated tools, skills and Swarm must remain discoverable and executable

系统 MUST 提供迁入 tools、skills 和 Swarm preset 的能力清单，并在合法请求下保持其原有输入输出语义。缺少依赖或权限不足的能力 MUST 标记为不可用并说明原因，而不能静默丢失。

#### Scenario: Query available capabilities
- **WHEN** 已认证用户请求 Agent 能力清单
- **THEN** 系统返回 tools、skills、Swarm preset、版本/来源标识和不可用原因

#### Scenario: Execute a migrated capability
- **WHEN** AgentLoop 调用合法 tool、skill 或 Swarm preset
- **THEN** 系统执行对应能力，将调用过程写入 trace，并发布结构化事件

### Requirement: Agent runtime must preserve trace and recovery semantics

系统 MUST 持久化 Agent 消息、attempt 状态、增量响应、工具轨迹、trace、Swarm run 和最终结果，并支持进程重启后的恢复或明确中断。

#### Scenario: Reconnect after SSE interruption
- **WHEN** 客户端使用最后事件游标重新连接
- **THEN** 系统按序补发未确认事件，且不重复执行同一个幂等任务

#### Scenario: Restart during an attempt
- **WHEN** Agent runtime 在 attempt 执行期间重启
- **THEN** 系统识别未完成 attempt，标记为可恢复或中断，并保留已有 trace 和部分响应
