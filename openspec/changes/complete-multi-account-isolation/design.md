## Context

当前 FastAPI 认证已经有数据库用户、JWT 和管理员创建用户，但 Token 主要以用户名为 subject，注册接口与页面不完整。业务路由虽大量使用认证依赖，仍存在历史 `admin` 默认值、共享文件目录、全局 runtime 状态和 Vibe Agent session/memory 目录；MongoDB 中不同资源的 owner 字段和过滤规则也不统一。详见 `proposal.md` 及四份 capability specs。

## Goals / Non-Goals

**Goals:**

- 建立以不可变用户 ID 为根的统一身份上下文和默认拒绝访问模型。
- 让 MongoDB、Redis、内存、文件系统、SSE/WebSocket、队列和 Agent runtime 使用同一 user scope。
- 提供普通用户注册和完整账户生命周期，同时兼容不伪造用户字段的已有客户端。
- 以迁移报告、隔离区和自动化越权测试证明数据不会串租户。

**Non-Goals:**

- 不把公共行情、静态市场元数据复制成每用户一份；公共数据仍可共享，但不得携带私人上下文。
- 不在本 change 中实现企业组织、团队共享、跨账号协作或复杂 RBAC；管理员跨用户访问只作为受审计的运维能力。
- 不改变 LLM provider 的配置格式、供应商账号体系或第三方 OAuth 登录。

## Decisions

### 1. 统一身份上下文

新增应用层 `UserContext`/认证依赖，解析并验证 access/refresh token 的类型、user ID、版本和账号状态。服务层 API 优先接收 context 中的 user ID；资源 owner 从 context 写入，禁止使用请求字段覆盖。选择 user ID 而非 username 是因为 username 可被未来修改，而资源归属必须稳定。保留短期旧 Token 兼容解析，但只允许映射到真实激活用户并在响应中换发新格式；不采用“仅检查 Bearer 前缀”的兼容方案。

### 2. Token 与会话撤销

access token 与 refresh token 使用不同类型和过期策略，refresh token 采用可轮换的服务端记录或版本号撤销模型；用户禁用、改密和退出可使对应版本失效。密码沿用现有强哈希能力并集中校验。选择服务端可撤销状态是因为纯 JWT 无法及时阻止禁用账号访问；不在浏览器保存密码，前端只保存最小必要 token 状态。

### 3. 数据层 owner 规范

定义资源分类清单和通用 owner 读写辅助函数，逐集合补字段、复合索引和查询过滤；新增/修改接口不接受 owner 参数。先覆盖已有个人资源和所有会产生个人数据的路径，再对公共集合明确标记为 global。选择逐集合显式过滤而非 MongoDB 全局 middleware，是为了避免误把公共行情过滤掉，也能让代码审查定位每个资源边界。

### 4. Runtime 和 Agent 隔离

为每个用户生成规范化 runtime root：`<data-root>/users/<user-id>/...`，session、run、trace、上传、搜索数据库和 persistent memory 均从该 root 派生。请求进入 runtime 时通过 context manager 注入 scope，退出时恢复；任何没有 scope 的持久化读写直接失败，不降级到默认 home、全局目录或 `admin`。搜索索引每用户独立或至少每次查询强制 user filter，优先独立索引以降低漏过滤风险。vendor 代码只通过已有 runtime directory/session/memory 接口扩展，必要时在应用层包裹，不修改无关第三方行为。

### 5. 异步和实时身份

创建任务时把 user ID 写入任务、Redis 消息和持久记录；worker 只信任服务端消息中的 owner，并在结果落库前再次校验。WebSocket 从握手 Token 解析用户，SSE 根据任务 owner 授权，忽略客户端 user id。选择“任务 owner + 请求用户双重检查”是为了防止任务 ID 泄露和 worker 消息错配。

### 6. 迁移与失败安全

迁移脚本先 dry-run，输出按集合的可映射、冲突、缺失和将进入隔离区的数量；正式迁移使用版本标记、幂等 upsert/更新和备份。无法证明归属的数据移动到受保护隔离集合或目录，普通查询永远排除。部署先启用观测/只读校验，再执行写迁移，最后打开强制隔离；回滚只回滚应用开关和迁移版本，不把不确定数据重新暴露给普通用户。

### 7. 测试策略

使用单元测试覆盖 Token、scope/path、owner helper 和记忆索引；使用 FastAPI 集成测试建立 A/B 两个用户验证每类资源的列表、详情、修改、删除、导出、SSE/WebSocket 和记忆召回；使用临时 MongoDB/Redis/文件 root 验证并发和重启后隔离；迁移测试覆盖重复执行、冲突、失败和回滚。CI 增加静态检查，禁止新增硬编码用户身份和无 scope 的个人持久化调用。

## Risks / Trade-offs

- [Risk] 历史记录无法可靠归属 → 迁移前 dry-run，无法映射者进入隔离区，默认不可见。
- [Risk] 某个旧路由漏加 owner 条件 → 统一审计清单、静态扫描和 A/B 越权集成测试；高风险接口在发布前逐项验收。
- [Risk] 每用户 runtime/索引增加文件和连接数 → 延迟创建、生命周期清理、限制配额，并保留按用户统计与运维清理接口。
- [Risk] Token 撤销检查增加请求开销 → 使用 Redis/短 TTL 缓存状态，账号状态变更主动失效缓存；安全边界优先于极限吞吐。
- [Risk] vendor session/memory 接口不支持 scope → 在应用层适配并补最小接口；没有安全 scope 时显式失败，而不是共享 fallback。
- [Risk] 现有客户端依赖全局配置或 `admin` → 提供迁移开关和兼容期诊断，但兼容期也不得向普通用户暴露无归属数据。

## Migration Plan

1. 发布仅包含 schema、索引、dry-run 和审计能力的版本，不打开强制隔离。
2. 备份用户相关集合及 runtime 根目录，运行 dry-run，人工确认映射规则和隔离区报告。
3. 执行幂等迁移和索引创建，校验 owner 覆盖率、冲突数、隔离区数量及抽样访问结果。
4. 部署后端统一身份、所有权过滤、runtime scope 和实时通道改造；先在日志中报告旧路径命中，再打开默认拒绝。
5. 部署前端注册和登录态更新，运行完整跨账号验收后移除旧的 `admin` fallback 和兼容开关。
6. 回滚时关闭新路由/前端入口并恢复应用版本；保留迁移备份和隔离区，禁止通过回滚把未归属数据恢复到普通查询。
