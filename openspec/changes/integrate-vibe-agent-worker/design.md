## Context

See proposal.md - Why.

当前项目已经有成熟的认证、任务中心、MongoDB/Redis、SSE、前端路由和分析页面；Vibe-Trading 则已经具备完整的自然语言研究运行时、trace、Swarm、skills 和 tools，但它的持久化和运行假设更接近单用户本地环境。这个变更的难点不在于“是否能跑”，而在于如何把研究能力接入现有多用户系统而不破坏隔离、任务可见性和现有分析链路。

## Goals / Non-Goals

**Goals:**
- 将 Vibe-Trading 的自然语言研究能力作为独立 Worker 模块接入 QuantingAgents。
- 前端工作台交互、SSE、工具轨迹和 Swarm 展示遵循 Vibe-Trading 的运行习惯。
- 用户身份、权限、任务中心和审计统一归 QuantingAgents。
- 文件型运行产物按用户和会话隔离。
- 保持现有单股分析、批量分析和报告链路不被影响。

**Non-Goals:**
- 不把 Vibe-Trading 的整套 Web 前端原样搬入主应用。
- 不重写现有 QuantingAgents 分析引擎。
- 不将 Worker 设计成对外公开的独立公网服务。
- 不在本次变更里实现新的交易权限模型或新的数据源体系。

## Decisions

### 1. 采用模块化 Worker，而不是直接 HTTP 独立服务

Worker 运行在独立进程/容器中，但由 QuantingAgents 统一调度，任务与事件通过 Redis 传递，前端只面对 QuantingAgents API。

**Rationale:** 这样可以保留运行隔离，同时避免前端到 Vibe 服务的额外鉴权、跨域和 SSE 代理复杂度。它比“完全独立 HTTP 服务”更容易统一任务中心，也比“完全合并进主 API”更容易隔离故障和依赖冲突。

**Alternatives considered:**
- 直接独立 HTTP 服务：隔离更强，但认证、SSE 和运维复杂度更高。
- 直接嵌入主服务：接线最短，但对主 API 的风险最大，且更难维护 Vibe 运行时边界。

### 2. 任务中心作为统一元数据层，文件系统作为运行产物层

MongoDB 保存用户、会话、任务、状态摘要和查询索引；trace、临时文件、Swarm 产物和更大的研究结果继续落文件系统。

**Rationale:** Vibe-Trading 的现有 trace 和 Swarm 产物是文件型的，短期内保留它们最稳。统一元数据层可以让 QuantingAgents 的任务中心承载跨分析类型的列表、状态和权限过滤，而不要求所有细节都立刻转成数据库模型。

### 3. 运行目录按用户和会话计算

每次研究请求都派生出独立的用户作用域运行根目录，并在其下再分 session、attempt、runs、swarm 和 uploads 子目录。

**Rationale:** 这是解决 Vibe-Trading 原始单用户假设的核心。只要所有文件读写都经过同一个运行根目录计算函数，就能避免跨用户串读、路径穿越和 trace 污染。

### 4. 前端工作台以 Vibe 交互为准，主应用只提供壳和权限

研究工作台页面负责展示自然语言输入、SSE 事件流、工具调用、ReAct 概览和 Swarm 状态。QuantingAgents 现有分析页面保持原样，不与 Agent 工作台共享交互状态。

**Rationale:** 用户明确要求 Agent 功能与现有分析功能完全隔离。前端共享导航和主题，但不共享业务状态，能减少互相影响。

### 5. 以幂等任务协议和事件协议贯穿 Worker

任务提交必须携带 user/session/task 标识，Worker 事件必须携带相同作用域。取消、恢复、重复提交都按幂等规则处理。

**Rationale:** SSE 和文件型持久化都容易出现重放和重复事件，没有幂等键和作用域就无法安全恢复，也无法和任务中心对账。

## Risks / Trade-offs

- [Redis 事件协议设计不稳] → 先定义极少字段、强类型事件 envelope，再逐步增加 payload。
- [文件型产物仍会增长] → 运行目录按用户分层，并加上清理、归档和可配置保留期。
- [Vibe 依赖与主项目依赖冲突] → Worker 进程使用独立环境；主 API 不直接 import 整个 Vibe 运行时。
- [SSE 重连和事件顺序出错] → 以单一事件游标和持久化事件序列号为准，不依赖客户端本地状态。
- [任务中心改动过大影响既有分析] → 新任务类型单独建模，现有单股/批量分析模型保持不变。
- [高风险工具误用] → 保留现有权限入口和审计记录，Worker 只执行经过授权的上下文。

## Migration Plan

1. 先落地研究工作台和任务协议，只接只读研究链路。
2. 接入 Worker 的 SSE、session 和 trace，确保用户隔离目录正确。
3. 迁移 tools、skills 和 Swarm 注册，保持能力对齐。
4. 将研究任务纳入任务中心的统一列表和状态页。
5. 再逐步开放写文件、上传和其他高风险工具，并补齐审计。
6. 若 Worker 或桥接层不稳定，可通过配置关闭研究工作台入口，回退到现有分析功能。

## Open Questions

- 运行目录的具体根路径是否与现有 `~/.vibe-trading` 保持名称兼容，还是切换为 QuantingAgents 自有前缀。
- Worker 是否采用单实例多用户模式，还是按用户/租户拆分多个进程池。
- 研究结果摘要进入任务中心时，保留到什么粒度的 trace 引用和证据链接。
