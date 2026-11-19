## Why

当前前端把算力充值的入口放在路由和特定页面内部，没有形成可发现的主导航入口；Agent 评测和自进化菜单又依赖 `VITE_EVAL_PLATFORM_ENABLED` / `VITE_EVOLUTION_ENABLED` 环境开关，导致管理员在不同部署环境下看到的菜单不一致。需要把充值、管理员功能入口和 AI 研究的导航优先级统一成角色化的稳定体验。

## Scope

本 change 只调整导航入口、菜单可见性、菜单顺序和“评测/自进化默认对管理员开放”的开关治理，不改变充值订单、支付、套餐、评测算法、自进化算法或普通用户投资分析流程。按需求解释，评测和自进化属于管理员可用的内置管理能力，不再由前后端 enable 开关决定是否展示或提供。

## Non-Goals

- 不重做算力充值支付页本身，不改支付服务商、订单幂等或到账逻辑。
- 不改变评测集、评分器、自进化触发、审批、发布和回滚的业务规则。
- 不改变普通用户可见的非管理功能菜单。
- 不引入新的权限系统，继续复用现有 `is_admin` / `requiresAdmin` 边界。

## What Changes

- 增加两个充值支付页入口：
  - 侧边栏底部增加固定“算力充值”按钮，侧边栏折叠时保留图标入口。
  - 顶部右侧增加可点击的算力余额入口，点击进入 `/token-recharge`。
- 侧边栏主菜单不重复放置“算力充值”入口。
- **BREAKING** 移除 `VITE_EVAL_PLATFORM_ENABLED` / `VITE_EVOLUTION_ENABLED` 对菜单展示和路由守卫的控制；Agent 评测、自进化菜单只根据管理员角色显示。
- **BREAKING** 移除后端 `EVAL_PLATFORM_ENABLED` / `EVOLUTION_ENABLED` 作为能力开关的用法；服务初始化、路由注册、接口可用性和自进化触发不再依赖这两个开关，管理员鉴权仍保留为最终防线。
- 系统管理一级菜单，以及设置中的配置管理、缓存管理，只对管理员显示和可访问；普通用户直接访问对应 URL 仍被前端守卫拦截，后端 API 保持管理员校验。
- 将“AI 研究”菜单调整到侧边栏第二个位置，紧随“工作台”之后。
- 清理 `.env`、`.env.example`、文档和测试中对上述已废弃开关的依赖，更新前端/后端回归测试。

## Capabilities

### New Capabilities

- `token-recharge-access`: 定义算力充值页从侧边栏菜单、侧边栏底部按钮和顶部算力余额入口可访问的产品契约。
- `navigation-menu-experience`: 定义 AI 研究在侧边栏中的固定顺序，以及导航入口的可发现性约束。

### Modified Capabilities

- `admin-access-hardening`: 扩充管理员专用导航边界，覆盖系统管理、配置管理、缓存管理、Agent 评测和自进化；菜单展示不再依赖 feature enable 环境配置。
- `agent-evaluation-platform`: 移除评测后台对 enable 开关的访问依赖，管理员账号默认可访问评测和自进化管理能力，普通用户仍不可访问。

## Impact

- **Frontend**: `SidebarMenu.vue`、`BasicLayout.vue`、`HeaderActions.vue`、`router/index.ts`、`types/router.d.ts`、`stores/tokenBilling.ts`、`utils/sidebarEntries.ts` 及对应前端测试。
- **Backend**: `app/core/config.py`、`app/main.py`、`app/routers/eval.py`、`app/routers/evolution.py`、自进化/评测服务中的 enable 判断及后端测试。
- **Config/Docs**: `.env`、`.env.example`、相关 README/guide 文档和测试夹具中的废弃开关。
- **Compatibility**: 删除前端两个 VITE 开关和后端两个 enable 配置字段属于 **BREAKING**；管理员功能将默认开放，不再支持通过这些配置在管理员侧隐藏功能。

## Acceptance Criteria

- 已登录管理员可从侧边栏底部按钮和顶部算力余额两个入口进入算力充值页；顶部余额展示当前算力余额，点击后跳转成功。
- 侧边栏主菜单不显示“算力充值”，普通用户也不会因为充值入口看到受保护管理功能。
- 已登录普通用户看不到 Agent 评测、自进化、系统管理、配置管理、缓存管理入口；直接访问对应 URL 被前端守卫拦截，后端接口仍返回 403。
- 管理员在 `VITE_EVAL_PLATFORM_ENABLED` / `VITE_EVOLUTION_ENABLED` 缺失或为 `false` 时，仍能看到并访问 Agent 评测和自进化页面。
- 后端在未配置 `EVAL_PLATFORM_ENABLED` / `EVOLUTION_ENABLED` 时仍初始化评测/自进化服务、注册路由并正常响应管理员请求。
- “AI 研究”位于侧边栏第二个位置，紧随“工作台”。
- 前端类型检查、前端测试和后端相关测试通过。
