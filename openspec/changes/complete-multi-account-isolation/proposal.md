## Why

项目已有数据库用户、JWT 登录和管理员创建用户的基础，但普通用户无法自主注册，且部分分析、会话、文件运行时、WebSocket 和 Agent 长期记忆仍可能使用共享作用域或历史 `admin` 默认值。多账号部署如果只补登录页面，会导致用户之间读取、检索或复用彼此数据，属于严重的越权和隐私问题，因此需要一次端到端的身份与租户隔离改造。

## What Changes

- 增加普通用户注册、注册输入校验、账号状态处理、密码策略、登录失败限流和完整的 Token 生命周期管理。
- 统一后端身份依赖和用户上下文，使用不可变用户 ID 作为数据归属依据，并补齐角色、管理员接口和资源所有权校验。
- 为分析任务、报告、自选股、通知、投资观察、配置、操作日志、评测资源、导入导出和其他用户可见资源建立明确的 owner/user scope；禁止通过请求参数切换到其他用户。
- 为文件会话、Vibe Agent session、workspace/run 目录、SQLite 搜索索引、短期任务内存和长期 persistent memory 建立按用户隔离的命名空间和访问检查；记忆召回、写入、删除和重建索引都必须带用户范围。
- 修复 WebSocket、SSE、后台任务和跨进程队列中的身份传递，连接和任务订阅必须绑定已验证用户，不能使用硬编码 `admin` 或客户端任意传入的 user id。
- 增加前端注册页、登录态恢复、退出、Token 刷新和账号信息交互，并确保路由守卫与后端行为一致。
- 提供旧数据迁移、未归属数据处理、回滚策略、审计日志和跨账号越权测试；对无法安全归属的数据默认不向普通用户暴露。
- **BREAKING**：受保护接口不再接受仅凭 URL/body/query 指定用户范围的访问；缺少 owner 或无法证明归属的历史资源将返回受控结果，而不是按全局数据返回。

## Capabilities

### New Capabilities

- `identity/multi-account-auth`: 普通用户注册、登录、Token、密码、账户状态和管理员用户管理契约。
- `security/tenant-isolation`: 统一用户上下文、资源所有权、角色授权、后台任务和实时连接的跨层隔离规则。
- `agent/user-scoped-memory`: Agent 会话、工作区、短期状态、搜索索引和长期记忆的用户级命名空间与生命周期。
- `data/user-owned-resources`: 用户业务资源、配置、分析结果、导入导出和历史数据迁移的归属与访问契约。

### Modified Capabilities

- 无。现有 `openspec/specs/` 中没有覆盖这些完整行为的稳定能力规范。

## Impact

- 后端：`app/routers/auth_db.py`、认证服务、用户服务、所有依赖 `get_current_user` 的路由、任务/队列/通知/WebSocket 服务、MongoDB 模型和索引、迁移脚本。
- Agent/runtime：`vibe_agent_runtime` 的 session store、persistent memory、搜索索引、workspace/run 路径和服务调用上下文；需要尊重 vendor 边界并通过已有接口扩展。
- 前端：`frontend/src/views/Auth`、认证 store/API、路由守卫、Vibe Agent 会话 UI、用户资料和错误处理。
- 配置与部署：JWT/refresh token、注册开关、限流、数据根目录、迁移开关和密钥配置；不改变已有模型供应商配置契约。
- 测试与运维：新增认证、越权、并发、WebSocket/SSE、记忆召回、迁移/回滚和多进程隔离测试；需要更新文档和部署检查项。
