# 多账号资源隔离清单

本文档是 `complete-multi-account-isolation` 的资源盘点基线。资源分为 `private`（必须按用户隔离）、`global`（可共享但不得混入私人上下文）和 `admin`（仅管理员或系统任务）。任何新增持久化资源必须在此登记 owner、访问入口和测试覆盖。

## 盘点规则

- 私有资源的 owner MUST 由服务端认证上下文派生，不能由请求 body、query、path 或前端本地状态决定。
- 未能证明归属的历史数据 MUST 进入隔离区，不能通过普通用户接口返回。
- Redis key、内存 key、文件路径和异步消息都属于资源边界，不能只检查 MongoDB。
- `admin` 不是普通用户的 fallback；系统任务必须使用明确的 system scope 并禁止读取私人资源，除非走审计过的管理员路径。

## MongoDB 资源

| 资源/集合 | 范围 | 主要入口 | 当前归属风险 | 目标验收 |
| --- | --- | --- | --- | --- |
| `users` | private/admin | `app/services/user_service.py`, `/api/auth` | 用户身份本身；用户名不是稳定 owner | 用 `_id` 作为 Token 和资源 owner，用户名仅用于登录/展示 |
| analysis/tasks/results | private | `app/services/analysis_service.py`, `simple_analysis_service.py`, analysis/report routers | 历史兼容 `admin`、`user`/`user_id` 字段不统一 | 创建写入 owner；列表、详情、取消、清理、统计全部 owner 过滤 |
| favorites/tags | private | `app/routers/favorites.py`, `tags.py` | 部分逻辑依赖请求参数 | 任何读写只使用认证 user id |
| notifications/news watch/observations | private | notifications/news_watch services and routers | 已有 user_id，但需逐入口验证 | 查询、更新、推送、聚合均带 owner |
| personal investment/paper | private | `app/models/personal_investment.py`, investment/paper routers | 需检查所有详情和导出路径 | owner immutable，跨用户资源返回受控 403/404 |
| user config/provider credentials | private | `app/routers/config.py`, config services | 共享配置与个人配置边界复杂 | API key、偏好和个人 preset 只属于当前用户，响应脱敏 |
| operation logs | private/admin | `operation_logs.py`, middleware | 系统日志可能有全局记录 | 普通用户只能看自己的日志，管理员跨用户访问有审计 |
| eval/evolution/scheduler/cache/sync metadata | admin/global or private | corresponding routers/services | 需显式分类，不能默认开放 | 每个 endpoint 标注范围并有路由测试 |
| market/reference data | global | stock/data/sync routers | 可能与个人筛选混合 | 公共数据可共享，不携带私人 prompt、配置或历史 |

## Redis、队列和内存

| 资源 | 范围 | 当前位置 | 目标验收 |
| --- | --- | --- | --- |
| pending/processing/quota/rate-limit keys | private | `app/core/redis_client.py` | key 必须包含 canonical user id；不能接受客户端 user id |
| task/session keys | private | queue and analysis services | 写入、读取、过期、重试和清理均校验 owner |
| notification/websocket routing | private | websocket manager and notifications service | connection、event、broadcast 只投递同一 user scope |
| analysis task memory | private | `app/services/memory_state_manager.py`, analysis services | 无 scope 操作显式失败；A/B list/get/cleanup 互不可见 |
| process-wide caches | global or private | cache services and module singletons | 私人结果不得进入 global cache；private key 必须有 user prefix |

## 文件和 Agent runtime

| 资源 | 范围 | 当前位置 | 目标验收 |
| --- | --- | --- | --- |
| uploads/exports/backups | private | `UPLOAD_DIR`, database routers/services | 路径包含 user scope；下载 token 绑定 owner；防目录穿越 |
| web file sessions | private | `web/utils/file_session_manager.py` | `data/sessions` 不再作为跨用户默认根目录 |
| Vibe session/messages | private | `vibe_agent_runtime/vendor/src/session` and `app/routers/vibe_agent.py` | session id 仅在用户 namespace 有效 |
| run/workspace/trace | private | runtime paths and AgentLoop | user-specific root；无 scope 不读写默认 home |
| persistent memory | private | `src/memory/persistent` integration and context builder | 写入、召回、删除、统计、索引重建均过滤 user scope |
| SQLite full-text index | private | `vibe_agent_runtime/vendor/src/session/search.py` | 独立 user index 或强制 owner filter；重建不能跨目录扫描 |
| skills/profile/connections/credentials | private/admin | runtime trading/profile modules | 凭据引用和画像不得进入全局配置或其他用户 prompt |

## 异步与实时入口

- 任务创建入口：analysis、batch、screening、sync、Vibe Agent。每个任务记录 MUST 携带 owner。
- worker 入口：`app/worker/` 及队列消费逻辑。worker 只信任服务端消息中的 owner，并在结果落库前复核。
- SSE：`app/routers/sse.py`。订阅前按任务 owner 授权。
- WebSocket：`app/routers/websocket_notifications.py`。握手 Token 派生 user id，禁止硬编码 `admin` 和客户端绑定。

## 当前已识别的高风险模式

- `user_id = "admin"` 等硬编码身份。
- 仅按资源 id 查询而未同时附加 owner 条件。
- file/session/search 使用进程全局或用户 home 目录。
- Agent persistent memory 在没有 user scope 时降级为共享存储。
- 请求中的 `user_id`、`owner_id`、`profile_id` 覆盖认证上下文。

## 验收记录

- 盘点状态：初始基线，待任务 4.x、5.x、6.x 逐项更新为已隔离。
- 清单审查命令：`rg -n "user_id|owner_id|profile_id|admin|sessions|memory|UPLOAD_DIR" app frontend web vibe_agent_runtime`。
- 完成标准：所有 private 行都有 owner 写入点、读写入口、索引/路径策略和 A/B 越权测试；未完成项不得打开强制隔离模式。
