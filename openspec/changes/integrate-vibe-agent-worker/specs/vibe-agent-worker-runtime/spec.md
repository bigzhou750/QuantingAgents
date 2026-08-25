## Purpose

为 QuantingAgents 提供一个与现有业务分析链路隔离的 Vibe Agent Worker 运行时，执行自然语言研究、ReAct、tools、skills 和 Swarm，并以用户和会话为边界安全保存文件型运行产物与审计记录。

## ADDED Requirements

### Requirement: Worker 接受带身份作用域的研究任务

Worker SHALL 只接受包含用户标识、会话标识、任务标识、请求内容和运行配置的有效任务。Worker MUST 拒绝缺少身份作用域或作用域格式无效的任务。

#### Scenario: 接受有效任务
- **WHEN** Worker 收到完整且可验证的用户、会话和任务上下文
- **THEN** Worker 创建一次独立执行尝试并开始运行 Agent

#### Scenario: 拒绝无身份任务
- **WHEN** Worker 收到缺少用户或会话归属的任务
- **THEN** Worker 拒绝执行并发布可关联的失败事件

### Requirement: Worker 运行目录必须按用户和会话隔离

Worker SHALL 将 session、attempt、trace、Swarm run、上传文件和生成产物写入由系统计算的用户/会话作用域目录。外部请求不得通过路径参数越权访问其他作用域。

#### Scenario: 创建用户运行产物
- **WHEN** Worker 为用户执行研究任务并生成 trace 或文件
- **THEN** 所有产物写入该用户和会话对应的运行目录，并记录稳定的相对引用

#### Scenario: 路径穿越或跨用户引用
- **WHEN** 请求包含路径穿越、绝对路径或其他用户作用域的文件引用
- **THEN** Worker 拒绝该请求，并且不读取、覆盖或删除目标路径

### Requirement: Worker 发布完整的任务生命周期事件

Worker SHALL 发布任务已接收、开始、消息增量、工具调用、工具结果、校验、证据、Swarm 更新、完成、失败、取消和恢复所需的结构化事件。每个事件 MUST 包含任务、会话和用户作用域。

#### Scenario: 研究任务正常完成
- **WHEN** Agent 完成自然语言研究
- **THEN** Worker 发布完成事件，包含最终结果引用、运行统计和可读取的 trace 标识

#### Scenario: Worker 或 Agent 异常
- **WHEN** Agent 执行异常、进程异常退出或工具链失败
- **THEN** Worker 发布失败或中断事件，并保留可恢复所需的状态和诊断信息

### Requirement: Worker 支持取消、恢复和幂等处理

Worker SHALL 支持按任务和执行尝试取消运行，并在重启后识别未完成任务。重复提交、重复取消和重复恢复请求 MUST 不产生重复执行或破坏已有终态。

#### Scenario: 取消运行中的任务
- **WHEN** Worker 收到授权任务的取消请求
- **THEN** 当前执行停止在安全边界，持久化终态，并发布取消事件

#### Scenario: Worker 重启后恢复任务
- **WHEN** Worker 启动并发现持久化状态显示任务仍在运行
- **THEN** Worker 将任务标记为可恢复、已中断或按策略重新执行，并发布状态修正事件

#### Scenario: 重复提交相同任务
- **WHEN** Worker 收到相同幂等键的重复任务
- **THEN** Worker 返回原任务标识或现有终态，不重复启动 Agent

### Requirement: 迁移的 tools、skills 和 Swarm 保持能力兼容

Worker SHALL 注册迁移范围内的 Vibe-Trading tools、skills 和 Swarm 能力，并保持其对合法输入的既有业务语义。迁移不得因接入 QuantingAgents 而无故移除能力。

#### Scenario: 查询可用能力
- **WHEN** 工作台或 Worker 请求能力清单
- **THEN** 系统返回可用 tools、skills 和 Swarm preset，并标识不可用能力及原因

#### Scenario: 执行迁移后的研究能力
- **WHEN** Agent 调用合法的 tool、skill 或 Swarm preset
- **THEN** Worker 按迁移前的语义执行，并将执行记录写入对应 trace 和任务事件

### Requirement: Worker 运行时与现有分析链路隔离

Worker SHALL 使用独立的进程入口、任务类型和运行目录，不得修改或接管现有 QuantingAgents 单股分析、批量分析和既有任务的执行逻辑。

#### Scenario: Agent Worker 发生故障
- **WHEN** Worker 进程崩溃或不可用
- **THEN** QuantingAgents 现有分析 API 和任务仍可按原逻辑运行，并将研究任务标记为不可用或失败

#### Scenario: 现有分析任务运行
- **WHEN** 用户提交现有单股或批量分析
- **THEN** 请求继续进入原有分析链路，不经过 Vibe Agent Worker
