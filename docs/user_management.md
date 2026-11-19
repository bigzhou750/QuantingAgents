# 用户管理

## 管理员账号管理页面

管理员登录后通过侧边栏“设置 -> 系统管理 -> 用户管理”进入，或直接访问 `/settings/users`。

页面支持：

- 查看已注册账号列表，按用户名/邮箱搜索，按正常、已禁用、已归档状态筛选。
- 查看单个账号的邮箱、角色、状态、验证状态、创建/更新时间、最后登录时间、配额和用量统计。
- 创建普通用户或管理员账号。
- 更新账号邮箱、每日配额和并发限制。
- 启用/禁用账号、设置/取消管理员角色。
- 重置密码。
- 安全归档账号。

只有 `is_admin=true` 的管理员可以访问该页面和调用对应接口，普通用户会收到 403。

## 后端接口

用户管理接口挂载在 `/api/auth` 下，沿用现有 JWT 认证和管理员审计日志：

| 功能 | 方法 | 路径 |
|------|------|------|
| 用户列表 | GET | `/api/auth/users` |
| 用户详情 | GET | `/api/auth/users/{username}` |
| 创建用户 | POST | `/api/auth/create-user` |
| 更新账号资料/配额 | PATCH | `/api/auth/users/{username}` |
| 启停账号 | PATCH | `/api/auth/users/{username}/status` |
| 角色变更 | PATCH | `/api/auth/users/{username}/role` |
| 重置密码 | POST | `/api/auth/reset-password` |
| 归档账号 | DELETE | `/api/auth/users/{username}` |

用户列表支持 `keyword`、`status`、`skip`、`limit` 参数，`total` 为满足筛选条件的完整数量。

## 归档语义

“删除账号”在后端采用安全归档流程：

- 账号先被禁用，再标记为 `is_archived=true`。
- 归档账号无法登录、刷新 Token 或继续访问受保护接口。
- 历史分析记录、任务、会话、记忆等资源不会被物理删除，保留原 owner 归属。
- 归档账号仍可通过管理页的“已归档”筛选查看，普通业务查询和登录路径不会返回它们。

## 说明

本文档描述的是 FastAPI/MongoDB 数据库认证体系中的用户管理。旧版 Streamlit 文件认证（`web/config/users.json`）仍由命令行脚本管理，两者不是同一套账号数据。
