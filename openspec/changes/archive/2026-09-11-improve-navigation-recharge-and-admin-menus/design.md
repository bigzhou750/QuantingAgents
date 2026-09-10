## Context

现有前端已经有算力计费 API 和 `tokenBilling` store，充值页与 Vibe Agent 工作台已经在使用余额展示；`HeaderActions` 只是没有接入该 store。侧边栏当前用 `VITE_EVAL_PLATFORM_ENABLED` / `VITE_EVOLUTION_ENABLED` 叠加管理员角色控制评测和自进化菜单，路由守卫也读取这些变量。后端在 `app/main.py`、`app/routers/eval.py`、`app/routers/evolution.py` 和自进化服务中仍用 `EVAL_PLATFORM_ENABLED` / `EVOLUTION_ENABLED` 决定能力是否注册和运行。

## Goals / Non-Goals

**Goals:**

- 让算力充值的三个入口复用现有 `tokenBilling` store 和 `/token-recharge` 路由，不新增计费 API。
- 让管理员菜单只依赖 `authStore.isAdmin`，前后端不再用 feature enable 开关门禁评测/自进化。
- 保持普通用户的非管理菜单稳定，并把 AI 研究固定到第二位置。

**Non-Goals:**

- 不重构 token billing 数据模型、订单状态机或支付 SDK。
- 不改变评测/自进化的业务规则，只调整初始化、路由注册和访问边界。
- 不引入 RBAC 表或新的角色字段，继续复用现有 `is_admin`。

## Decisions

### D1. 顶部余额入口复用 `tokenBilling` store

在 `HeaderActions.vue` 中接入 `useTokenBillingStore`，登录态建立后调用 store 的余额加载；直接使用现有 `balanceDisplay` getter 展示余额。点击余额区域使用 `router.push('/token-recharge')`，不新增请求。

**Alternatives considered:**

- 在 `BasicLayout` 中单独拉取余额：会增加重复状态，且无法复用充值页/Vibe Agent 已有的 store 行为。

### D2. 充值入口只放在侧边栏底部，不放入主菜单

侧边栏底部在 `BasicLayout.vue` 的 `.sidebar-footer` 中、`UserProfile` 上方增加固定按钮；折叠态隐藏文字只显示图标，保证管理员和普通用户都能进入。侧边栏主菜单不增加 `/token-recharge` 菜单项，避免与顶部余额入口重复。

**Alternatives considered:**

- 主菜单再放一个“算力充值”入口：与底部按钮和顶部余额入口重复，用户明确要求删除。

### D3. AI 研究固定为第二个菜单项

将 `/research-agent` 菜单项移到 `/dashboard` 之后、股票分析之前。菜单顺序由 `SidebarMenu.vue` 模板顺序唯一决定，不依赖路由配置或环境变量。

### D4. 前端管理员菜单改为纯角色判断

`SidebarMenu.vue` 中 `showEvaluationPlatform` 和 `showSelfEvolution` 改为 `authStore.isAdmin`；删除 `VITE_EVAL_PLATFORM_ENABLED` / `VITE_EVOLUTION_ENABLED` 判断。`router/index.ts` 删除 `requiresEvalPlatform` 守卫和 evolution 路径前缀守卫，`types/router.d.ts` 删除 `requiresEvalPlatform` 字段。系统管理和设置里的配置/缓存管理继续由现有 `authStore.isAdmin` 与 `requiresAdmin` 控制，并补充回归测试。

### D5. 后端评测/自进化为默认启用

从 `app/core/config.py` 删除 `EVAL_PLATFORM_ENABLED` 和 `EVOLUTION_ENABLED` 字段；`app/main.py` 无条件初始化评测、自进化服务并注册对应路由。`app/routers/eval.py`、`app/routers/evolution.py` 删除 enable 开关拒绝逻辑，状态接口不再提示“需要开启配置”。`runner_service.py`、`trigger_service.py` 中依赖 `EVOLUTION_ENABLED` 的判断一并移除。`ONLINE_BADCASE_ENABLED` 和 `EVOLUTION_SCHEDULE_CRON` 等独立子功能配置继续保留。

**Alternatives considered:**

- 仅删除前端开关、保留后端开关：管理员会看到菜单但接口返回未启用，违背“管理员可查看”的目标。
- 保留配置字段但忽略其值：会留下“配置已删除但文档仍存在”的误导，无法满足用户明确去掉配置的要求。

### D6. 前端与后端部署必须同步

删除前端开关后，若只发布前端，管理员菜单会先出现而后端路由未注册；删除后端开关后，若只发布后端，旧前端仍可能被 `VITE_*` 拦截。因此本 change 的前后端改动应作为一个发布单元提交和部署。

## Risks / Trade-offs

- [Risk] 评测和自进化不再支持部署级关闭，服务初始化成本固定存在。→ 保留 `ONLINE_BADCASE_ENABLED`、`EVOLUTION_SCHEDULE_CRON` 等子开关，避免把全部子能力都常驻。
- [Risk] 删除配置字段会导致现有测试、部署脚本或文档引用报错。→ 同步更新 `.env`、`.env.example`、相关 docs、测试夹具和测试断言，并在验收中扫描残留引用。
- [Risk] 顶部余额请求失败可能影响导航体验。→ `tokenBilling` store 已捕获错误，入口显示加载中/未知状态并保持可点击，不阻塞其他头部按钮。
- [Risk] 菜单顺序测试容易退化成字符串扫描。→ 复用现有 `sidebarEntries` 测试模式，同时断言 AI 研究索引和充值入口存在。

## Migration Plan

1. 先改前端导航与权限：充值入口、AI 研究排序、菜单角色判断、路由守卫清理。
2. 再改后端配置和服务初始化，确保前端发布后接口立即可用。
3. 清理环境配置、文档和测试中的废弃开关。
4. 执行前端类型检查、前端测试、后端相关测试和管理员/普通用户角色走查。
5. 回滚策略：本 change 无数据迁移；若需回滚，恢复 `app/core/config.py` 字段、`app/main.py` 条件初始化和前端 `VITE_*` 判断即可，但需前后端一起回滚。

## Test Strategy

- 前端单元测试覆盖：侧边栏包含三个充值入口、AI 研究位于第二、评测/自进化菜单不再依赖 env、普通用户看不到管理入口。
- 前端路由测试覆盖：普通用户直接访问 `/evaluation/*`、`/evolution/*`、`/settings/config`、`/settings/cache` 被拦截。
- 后端测试覆盖：无 enable 配置时评测/自进化路由注册成功、管理员请求成功、普通用户请求返回 403；自进化触发不再因 enable 配置被短路。
- 手动验收：管理员和普通用户分别走查侧边栏、顶部余额、折叠态、移动端抽屉和直接 URL。
