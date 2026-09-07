## Context

当前项目已经有数据库用户模型、JWT 登录、公开注册和管理员基础接口：

- 后端 `app/routers/auth_db.py` 已提供 `create-user`、用户列表、启停账号、角色变更和重置密码接口，并已接入 `log_operation` 审计。
- `UserResponse`/`list_users` 没有返回 `is_admin`，也没有用户详情、管理员更新资料/配额、删除归档接口。
- 前端已有登录注册、认证 store、`requiresAdmin` 路由守卫和 `/settings` 页面，但没有账号管理页面，也没有封装管理员用户接口。
- `complete-multi-account-isolation` 已定义用户资源归属性、不可变 user ID 和租户边界；账号管理不能绕过这些边界，也不能物理删除其他用户资源。

## Goals / Non-Goals

**Goals:**
- 提供一个仅管理员可见的 `/settings/users` 账号管理页面，覆盖列表、检索、分页、详情、创建、启停、角色、密码重置、资料/配额更新和删除归档。
- 复用现有 `app/routers/auth_db.py`、`user_service`、审计日志和前端 `requiresAdmin` 权限体系，尽量不引入新的认证模型。
- 删除账号采用安全归档语义，保留用户历史资源的数据归属，只切断登录和普通可见性。

**Non-Goals:**
- 不实现物理清理用户分析记录、任务、会话或记忆的批量删除工具。
- 不实现企业组织、团队共享、多租户外部协作或复杂 RBAC。
- 不改造旧 Streamlit 文件认证体系；本次只管理 FastAPI/MongoDB 数据库认证账号。
- 不新增邮箱验证、邀请码、SSO/OAuth 或计费系统。

## Decisions

### 1. 继续扩展 `/api/auth`，不另建 admin 路由

现有管理员接口、依赖注入和审计日志都在 `auth_db` 中，继续使用同一 router 可以复用 `get_current_user`、`get_current_admin`、`log_operation` 和现有测试夹具。新增接口统一挂到 `/api/auth/users/...`，保持客户端认知一致。

备选方案是新建 `/api/admin/users`，但它会复制依赖和审计逻辑，也会让现有接口与新页面维护两套入口；本次不采用。

### 2. 用户列表返回管理视图字段并修正分页统计

`UserResponse` 增加 `is_admin`，`user_service.list_users()` 在构造响应时带入该字段。列表接口新增 `keyword`、`status`、`skip`、`limit` 参数，`total` 必须来自独立 count 查询而不是当前页长度，保证前端分页准确。

新增 `UserAdminResponse` 承载详情接口，包含用户名、邮箱、角色、激活状态、验证状态、创建/更新时间、最后登录时间、偏好、配额和用量统计，不包含 `hashed_password`、refresh sessions 或 Token。

### 3. 保留现有接口，新增详情、更新和归档接口

计划接口：

- `GET /api/auth/users`：扩展为支持关键字、状态、分页和总数。
- `GET /api/auth/users/{username}`：返回单个账号的非敏感详情。
- `PATCH /api/auth/users/{username}`：更新邮箱、每日配额和并发限制。
- `DELETE /api/auth/users/{username}`：先禁用、再标记归档。
- 保留 `POST /api/auth/create-user`、`POST /api/auth/reset-password`、`PATCH /api/auth/users/{username}/status`、`PATCH /api/auth/users/{username}/role`。

所有管理员接口继续由管理员校验保护；新增接口优先使用现有 `get_current_admin`，旧接口保持现有鉴权方式，不做破坏性重构。

### 4. 归档采用 `is_archived` 标记而非物理删除

`User` 模型增加 `is_archived: bool = False`。归档操作设置 `is_archived=true` 和 `is_active=false`，并递增 `token_version` 使现有 Token 失效。登录、刷新和 `get_current_user` 对归档账号按禁用账号处理。用户拥有的资源不删除，继续保留原 owner 归属，避免破坏租户隔离和历史报告关联。

管理员账号管理页面仍可在“已归档”筛选中看到归档账号；普通用户数据查询和登录路径不会看到它们。归档账号的用户名/邮箱默认继续占用唯一索引，避免数据引用歧义。

备选方案是物理删除 `users` 文档，但它会让历史资源 owner 失去解析能力，并破坏审计和数据安全，因此不采用。

### 5. 防止管理员自我锁定

状态变更、角色变更和归档接口都禁止对当前登录管理员执行会移除自己访问能力的操作：不能把自身降为普通用户、不能禁用或归档自身。已有角色接口已阻止移除自身管理员角色，本次在状态和归档接口补齐同类保护。

### 6. 前端使用现有设置体系新增管理页

- 新增 `frontend/src/views/System/UserManagement.vue`，登录 `settings` 路由组下注册为 `/settings/users`，`meta.requiresAdmin=true`。
- 在侧边栏“系统管理”子菜单增加“用户管理”。
- 在 `frontend/src/api/auth.ts` 增加管理员用户 API 封装，并在 `frontend/src/types/auth.ts` 增加管理员视图类型。
- 页面使用 Element Plus 表格、筛选、分页、详情抽屉/对话框、创建用户表单和二次确认对话框。
- 重置密码由管理员输入符合策略的新密码，后端不返回、也不记录明文密码。

### 7. 审计与错误处理

所有创建、更新、启停、角色、密码重置、归档操作都通过 `log_operation(ActionType.USER_MANAGEMENT)` 记录操作者、目标用户名和结果。普通用户调用任一接口返回 403；目标不存在返回 404；重复用户名/邮箱返回 409。前端根据这些状态显示空状态、加载状态和可恢复的错误提示。

## Risks / Trade-offs

- [Risk] 归档账号仍占用用户名/邮箱唯一索引，短期无法重新注册同名账号 → 默认保留引用完整性；如需释放标识，后续单独做“释放归档标识”功能。
- [Risk] 旧客户端依赖当前用户列表响应，新增 `is_admin` 和分页字段属于增量变化 → 只增加字段，不删除现有字段，不改变默认返回结构。
- [Risk] 管理员误禁用或归档自身导致管理面锁定 → 在状态/归档接口增加当前账号保护，并保留审计和回滚入口。
- [Risk] 列表查询关键字使用宽松匹配可能带来性能问题 → 在 `users` 集合保留用户名/邮箱唯一索引，并限制 `limit` 上限和关键字长度。
- [Risk] 归档流程若后续误升级为物理删除会破坏资源归属 → 设计上归档只改账号状态，物理清理作为独立 change 评估。

## Migration Plan

1. 部署后端：给 `User` 模型增加 `is_archived` 默认值，给 `UserResponse` 增加 `is_admin`，新增详情、更新和归档接口；现有文档缺省值自动生效，不需要数据回填。
2. 部署前端：新增 API 类型、管理接口封装、`/settings/users` 页面和侧边栏入口。
3. 执行后端测试、前端构建/组件测试和权限矩阵测试，确认普通用户 403、管理员操作审计、归档账号不可登录。
4. 回滚：前端先移除页面与菜单；后端新增字段和接口为增量，可保留并继续兼容旧客户端。归档操作不会修改其他资源集合，因此回滚不需要迁移数据。

## Open Questions

- 归档账号的用户名/邮箱是否需要在未来释放复用？默认不释放；该决策不影响本 change 的接口和页面结构。
