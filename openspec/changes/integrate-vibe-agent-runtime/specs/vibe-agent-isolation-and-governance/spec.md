## Purpose

在迁入完整 Agent runtime 的同时，统一使用 QuantingAgents 的用户身份、权限、任务、审计和文件隔离边界，防止 Vibe 原有单用户文件持久化模型造成跨用户访问或高风险工具失控。

## ADDED Requirements

### Requirement: Every Agent execution must carry trusted user scope

每次 session、attempt、task、事件、trace、工具调用和 Swarm run MUST 绑定 QuantingAgents 认证用户、用户角色、session 和 task 标识。客户端提交的归属字段 MUST NOT 覆盖服务端认证上下文。

#### Scenario: Unauthorized session access
- **WHEN** 用户访问其他用户的 session、task、event 或 artifact 标识
- **THEN** API 返回拒绝或不存在，不泄露目标对象内容

#### Scenario: Forged execution context
- **WHEN** 请求体携带与当前登录用户不一致的 user/session/task 字段
- **THEN** 系统使用服务端认证上下文创建任务，并记录拒绝或修正信息

### Requirement: File runtime data must be isolated and path-safe

系统 MUST 将运行数据写入 QuantingAgents 配置的持久化根目录下的用户/session 子目录。所有外部路径引用 MUST 拒绝绝对路径、路径穿越和跨用户路径。

#### Scenario: Create isolated runtime data
- **WHEN** 用户执行研究任务并生成 trace、上传文件、Swarm run 或报告
- **THEN** 产物只写入该用户/session 的运行目录，并保存稳定的相对引用

#### Scenario: Path traversal attempt
- **WHEN** 请求尝试读取或写入 `../`、绝对路径或其他用户目录
- **THEN** 系统拒绝请求且不触碰目标路径

### Requirement: High-risk Agent operations must be permissioned and audited

写文件、Shell、外部 MCP、交易连接和其他高风险工具 MUST 经过服务端权限策略；每次调用 MUST 记录用户、工具、参数摘要、结果、错误和时间信息。默认配置 MUST 采用最小权限。

#### Scenario: High-risk tool denied
- **WHEN** 用户没有对应权限或工具未被管理员启用
- **THEN** 工具调用被拒绝，事件和审计日志记录拒绝原因

#### Scenario: Audited tool execution
- **WHEN** 高风险工具被允许执行
- **THEN** 系统在执行前后记录审计上下文，并将脱敏后的调用轨迹关联到 task 和 trace

### Requirement: Existing analysis workflows must remain isolated

内置 Agent runtime MUST 使用独立任务类型、路由和运行目录，不得修改现有单股分析、批量分析、报告和任务执行逻辑的行为契约。

#### Scenario: Existing single analysis
- **WHEN** 用户提交现有单股分析任务
- **THEN** 请求继续进入原有分析链路，不经过 Agent runtime

#### Scenario: Agent runtime unavailable
- **WHEN** 内置 Agent runtime 不可用
- **THEN** 现有股票分析 API 仍可用，研究任务明确返回不可用或失败状态
