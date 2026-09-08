## Purpose

为 QuantingAgents 提供独立的自然语言金融研究工作台，让用户从输入框进入迁入的 AgentLoop，并实时查看文本、工具、证据、ReAct、Swarm、trace 和最终研究结果。

## ADDED Requirements

### Requirement: Workbench must provide an isolated research conversation

研究工作台 MUST 提供会话列表、创建会话、消息输入、历史消息、任务状态和结果查看能力，并且不得共享现有单股分析页面的业务状态。

#### Scenario: Create and select a session
- **WHEN** 用户进入研究工作台并创建或选择会话
- **THEN** 页面只加载当前用户可访问的会话和消息，并建立对应 SSE 连接

#### Scenario: Submit a message
- **WHEN** 用户提交非空研究问题
- **THEN** 页面显示用户消息、任务入队状态和 Agent 的流式响应

### Requirement: Workbench must render structured Agent events

页面 MUST 展示文本增量、工具调用和结果、证据引用、ReAct 摘要、Swarm 状态、错误、完成和取消事件，并保留可重连的事件游标。

#### Scenario: Tool and evidence events arrive
- **WHEN** Agent 执行工具并产生证据
- **THEN** 页面在对应视图中显示工具名称、阶段、结果摘要、证据引用和关联任务

#### Scenario: Agent completes or fails
- **WHEN** Agent 完成、失败或被取消
- **THEN** 页面更新任务终态，显示最终结果或可读错误，并提供进入任务中心/研究会话的入口

### Requirement: Workbench must support cancellation and recovery

页面 MUST 提供取消、重连和错误恢复交互。重连 MUST 使用服务端事件序列恢复，而不是依赖浏览器内存中的文本状态。

#### Scenario: Cancel a running task
- **WHEN** 用户取消 queued 或 processing 状态的研究任务
- **THEN** 页面发送取消请求，显示 cancelled 终态，并停止继续追加该任务的流式输出

#### Scenario: Reload the workbench
- **WHEN** 用户刷新页面或重新打开已有会话
- **THEN** 页面从服务端加载历史消息和事件，恢复任务/轨迹展示
