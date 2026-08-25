## Context

See proposal.md - Why.

当前 QuantingAgents 已经有认证、MongoDB/Redis、任务中心、SSE、前端路由和现有股票分析服务；现有实验代码通过 child process 引用外部 Vibe-Trading 源码，无法满足源码整体迁入、可部署性和能力可见性要求。Vibe-Trading 的 AgentLoop 依赖 session、tools、skills、Swarm、trace、memory、provider/config 等一组相互关联的模块，不能只复制单个入口文件。

## Goals / Non-Goals

**Goals:**

- 将 Vibe Agent runtime 的完整可运行依赖闭包迁入 QuantingAgents。
- 让研究工作台输入直接进入本地迁入的 Agent session 和 AgentLoop。
- 保持 Vibe tools、skills、Swarm、trace、恢复和取消语义。
- 用 QuantingAgents 的认证、权限、任务、审计和用户隔离包住 Agent runtime。
- 保持现有单股分析、批量分析和报告链路不变。
- 明确迁移源清单、许可证边界、依赖冲突和能力发现结果。

**Non-Goals:**

- 不迁入 Vibe-Trading 原有独立 Web API、桌面 UI 或重复鉴权系统。
- 不把 Vibe 的所有业务产品功能无差别复制到 QuantingAgents。
- 不重写 QuantingAgents 现有股票分析引擎。
- 不在本次变更中开放默认 Shell、交易下单或任意 MCP 写操作。

## Decisions

### 1. 采用内部 vendored runtime，而不是外部源码路径

迁入的代码放在 QuantingAgents 明确的内部 runtime 包中，例如 `app/vibe_agent_runtime/` 或项目约定的 `vendor/` 边界。运行时只从该包加载，不读取 `VIBE_TRADING_SOURCE_ROOT`。

**Rationale:** 外部绝对路径只适合开发机实验，无法部署、打包、升级和审计；内部包才能满足用户要求的“整个代码移过来”。

**Alternative considered:** 保留 child process 并通过 `PYTHONPATH` 指向 Vibe 仓库。该方案启动快，但仍是外部依赖，能力清单、版本和许可证边界不在 QuantingAgents 内可控，因此不采用。

### 2. 迁移“运行时依赖闭包”，不迁入重复 Web 层

迁移范围以 AgentLoop 可运行所需的模块闭包为准：session、agent、tools、skills、swarm、trace/checkpoint、memory、provider/config 和它们直接依赖的 quantlib/backtest/data adapters。Vibe 原有 API routes、Web server 和独立前端不迁入。

**Rationale:** AgentLoop 的工具和技能不是孤立文件；迁移依赖闭包可以避免运行时缺模块，同时避免引入第二套 HTTP/API 生命周期。

### 3. 使用 QuantingAgents adapter 注入身份和存储

迁入 runtime 保留 AgentLoop 的业务语义，通过 adapter 注入 QuantingAgents 的用户 principal、session/task 标识、运行根目录、权限策略、审计回调和事件发布器。客户端不能直接控制 provider、MCP command、文件根目录或高风险开关。

**Rationale:** 这样既能保持 Vibe runtime 行为，也能阻断其原始单用户环境假设。

### 4. 采用本地进程内执行接口，Worker 只作为可选隔离边界

默认链路由 API/应用服务调用本地迁入的 runtime facade；如果保留 Worker，则 Worker 只能加载 QuantingAgents 内部 runtime 包，不能再通过 source root 启动外部 child。两种入口共享同一套 task/event/trace contract。

**Rationale:** 用户要求输入框到 AgentLoop 的完整本地链路；可选进程隔离保留故障边界，但不能再成为外部源码桥接。

### 5. 文件产物使用 QuantingAgents 运行根目录

运行目录由配置指定，默认使用 QuantingAgents 管理的持久化数据目录��不与源码目录混合：

```text
<runtime_root>/users/<user_id>/sessions/<session_id>/
  messages/
  attempts/
  runs/
  swarm/
  trace/
  uploads/
  artifacts/
```

所有工具只接受经过 scope 校验的相对路径。

### 6. 能力清单和迁移诊断是一等输出

runtime 启动时生成工具、技能和 Swarm preset 的能力清单，包含注册成功、不可用依赖、权限禁用和导入失败原因；研究工作台和健康接口可以查询该清单。

**Rationale:** 解决“代码迁入但功能静默缺失”的问题，便于验证 78 个左右工具模块和技能目录是否真的可用。

### 7. 许可证和上游同步作为迁移门禁

迁移前扫描 Vibe 源码许可证、第三方依赖和文件头声明；保留来源说明和版本记录。任何受限代码、秘钥、用户数据和本地 runtime 产物不得进入 QuantingAgents 的源码提交。

## Risks / Trade-offs

- [迁移依赖闭包较大] → 先建立文件/模块清单和导入诊断，再按 runtime 层次迁移；不以“能 import 入口”作为完成标准。
- [Vibe 与 QuantingAgents 依赖冲突] → 对 provider、config、memory 和数据源做适配层；必要时拆分可选依赖并增加隔离测试。
- [工具数量多且部分依赖缺失] → 启动时输出能力清单；每个不可用工具必须有明确原因，不能静默过滤。
- [高风险工具扩大权限边界] → 默认禁用 Shell/交易写操作/MCP 注入，按 QuantingAgents 权限策略和审计回调逐项开放。
- [迁移后上游同步困难] → 记录上游 commit、迁移映射和局部补丁，保持 vendored runtime 与业务 adapter 分层。
- [运行产物污染源码目录] → 默认 runtime root 指向独立持久化数据目录，并提供环境变量/配置覆盖。

## Migration Plan

1. 盘点 Vibe runtime 的模块、工具、技能、Swarm preset、许可证和依赖闭包。
2. 创建内部 runtime 包和来源清单，先迁入 session/agent 基础层及最小可运行闭环。
3. 迁入 tools/registry、skills/loader、trace/memory 和 provider/config 适配。
4. 迁入 Swarm runtime、store、worker、preset 和事件映射。
5. 将 QuantingAgents 研究 API、SSE、任务中心和前端输入接到内部 runtime facade。
6. 加入用户隔离、权限审计、能力清单、失败恢复、取消和幂等。
7. 运行迁移 runtime 测试、前端测试、SSE/E2E 测试以及单股/批量分析回归。
8. 旧 child/source-root 桥接仅保留迁移期间兼容开关；内部 runtime 验证通过后删除。

## Open Questions

- 迁入代码的最终顶层目录在 `app/vibe_agent_runtime/` 与 `vendor/vibe_agent/` 之间需要结合仓库许可证和打包规则确定；不改变外部行为契约。
- 上游 Vibe 版本固定到当前工作区 commit 还是发布 tag，需要在迁移清单阶段锁定。
