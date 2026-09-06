## 1. 后端数据模型与服务层

- [x] 1.1 在 `app/models/user.py` 给 `User` 增加 `is_archived` 默认字段，给 `UserResponse` 增加 `is_admin`，新增不包含密码哈希/Token 的 `UserAdminResponse`，验证 Pydantic 模型导入和字段序列化测试通过
- [x] 1.2 重构 `app/services/user_service.py::list_users`，支持 `keyword`、`status`、`skip`、`limit`，返回独立 `total`，并在响应中带入 `is_admin`，验证列表字段、筛选和总数测试通过
- [x] 1.3 在 `app/services/user_service.py` 新增 `get_user_admin_detail`、`update_user_admin`、`archive_user` 方法，验证存在/不存在、重复邮箱、配额边界和归档状态测试通过
- [x] 1.4 更新登录、刷新和 `get_current_user`，归档账号 MUST 与禁用账号一样被拒绝，验证认证测试覆盖归档账号登录和刷新
- [x] 1.5 确认 `archive_user` 只修改账号状态和 `token_version`，不删除用户资源集合，验证归档后用户资源 owner 保持不变

## 2. 后端管理员 API

- [x] 2.1 扩展 `GET /api/auth/users`，增加 `keyword`、`status`、`skip`、`limit` 参数和准确 `total`，验证管理员可检索、普通用户返回 403
- [x] 2.2 新增 `GET /api/auth/users/{username}` 管理员详情接口，验证成功返回非敏感详情、不存在返回 404、普通用户返回 403
- [x] 2.3 新增 `PATCH /api/auth/users/{username}` 管理员更新接口，支持邮箱、每日配额和并发限制，验证成功、重复邮箱、非法值和普通用户越权场景
- [x] 2.4 新增 `DELETE /api/auth/users/{username}` 归档接口，先禁用再归档，验证普通用户删除成功、当前管理员自删除被拒绝、归档后登录被拒绝
- [x] 2.5 为现有状态和角色接口补齐自我保护：不能禁用或归档当前登录管理员，不能移除自身管理员角色，验证对应 400/403 测试通过
- [x] 2.6 为新增和现有管理员操作接入 `log_operation(ActionType.USER_MANAGEMENT)`，验证审计记录包含操作者、目标用户、操作类型和结果

## 3. 前端类型与 API 封装

- [x] 3.1 在 `frontend/src/types/auth.ts` 增加管理员用户摘要、详情、列表响应、创建/更新/重置密码表单类型，验证 `npm run typecheck` 通过
- [x] 3.2 在 `frontend/src/api/auth.ts` 增加 `adminListUsers`、`adminGetUser`、`adminCreateUser`、`adminUpdateUser`、`adminUpdateUserStatus`、`adminUpdateUserRole`、`adminResetPassword`、`adminArchiveUser`，验证 TypeScript 类型检查和 mock API 测试通过

## 4. 前端账号管理页面

- [x] 4.1 新增 `frontend/src/views/System/UserManagement.vue`，实现账号表格、关键字搜索、状态筛选和分页，验证组件测试覆盖列表渲染和筛选请求
- [x] 4.2 实现账号详情展示，包含用户名、邮箱、角色、状态、验证状态、时间、配额和用量，验证界面不展示密码/Token 字段
- [x] 4.3 实现管理员创建用户表单，包含用户名、邮箱、密码和角色选项，验证必填、密码策略、重复错误和成功反馈测试通过
- [x] 4.4 实现启用/禁用、角色变更、重置密码、更新资料/配额和归档操作，验证每个高风险操作都先弹二次确认
- [x] 4.5 实现加载状态、空状态、错误提示和操作失败后列表状态保持，验证对应组件测试通过

## 5. 路由与权限导航

- [x] 5.1 在 `frontend/src/router/index.ts` 注册 `/settings/users`，设置 `requiresAdmin: true`，验证管理员可进入、普通用户被路由守卫拒绝
- [x] 5.2 在侧边栏“设置 -> 系统管理”增加“用户管理”菜单项，验证管理员可见、普通用户不可见

## 6. 测试与发布检查

- [x] 6.1 扩展 `tests/test_auth_admin_routes.py`，覆盖列表检索/分页、详情、更新、归档、自我保护和审计断言，验证 `pytest tests/test_auth_admin_routes.py -q` 通过
- [x] 6.2 增加或更新前端组件/路由测试，验证 `npm run test:unit`（或项目现有前端测试命令）通过
- [x] 6.3 运行前端构建、后端相关测试和 `openspec validate`，确认本 change 无语法、类型和 spec 校验错误
- [x] 6.4 更新数据库账号管理相关文档，说明 `/settings/users`、接口清单和归档语义，验证文档与实现一致
