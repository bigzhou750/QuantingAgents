## 1. 前端充值入口

- [x] 1.1 从 `SidebarMenu.vue` 主菜单移除 `/token-recharge` 菜单项，保留侧边栏底部与顶部入口（验证：`SidebarMenu.vue` 不包含 `index="/token-recharge"`，`npm run test:unit -- --run` 通过）
- [x] 1.2 在 `BasicLayout.vue` 侧边栏底部增加固定“算力充值”按钮，折叠态显示图标、展开态显示文字，点击跳转 `/token-recharge`（验证：代码审查确认按钮存在且点击处理路由跳转）
- [x] 1.3 在 `HeaderActions.vue` 增加顶部算力余额入口，接入 `useTokenBillingStore` 展示余额并支持点击跳转 `/token-recharge`（验证：调用 `npm run type-check` 通过，余额加载失败时不阻断头部其他操作）
- [x] 1.4 更新导航测试，移除侧边栏主菜单充值断言，并断言底部/顶部充值入口仍存在（验证：`npm run test:unit -- --run` 通过）

## 2. 前端菜单与管理员权限

- [x] 2.1 将 `/research-agent` 菜单项移动到 `/dashboard` 后的第二个位置，并更新菜单顺序测试（验证：`SidebarMenu.vue` 中 AI 研究在股票分析之前；`npm run test:unit -- --run` 通过）
- [x] 2.2 将 `SidebarMenu.vue` 中 `showEvaluationPlatform` / `showSelfEvolution` 改为仅 `authStore.isAdmin`，删除 `VITE_EVAL_PLATFORM_ENABLED` 与 `VITE_EVOLUTION_ENABLED` 判断（验证：`rg VITE_EVAL_PLATFORM_ENABLED frontend/src` 无命中）
- [x] 2.3 从 `router/index.ts` 删除 `requiresEvalPlatform` 守卫、evolution 路径 enable 守卫及相关 `import.meta.env` 判断（验证：`rg requiresEvalPlatform frontend/src/router frontend/src/types` 无命中）
- [x] 2.4 从 `types/router.d.ts` 删除 `requiresEvalPlatform` 元数据字段并移除所有路由中的该标记（验证：前端类型检查通过，`rg requiresEvalPlatform frontend` 无命中）
- [x] 2.5 复核 `Settings/index.vue` 与 `SidebarMenu.vue` 的系统管理、配置管理、缓存管理权限，确保普通用户不可见且 `requiresAdmin` 守卫保留（验证：普通用户测试断言不渲染管理入口）
- [x] 2.6 新增前端菜单/路由权限测试，覆盖管理员无 env 配置仍可见评测/自进化、普通用户看不到管理入口且直接访问 URL 被拦截（验证：`npm run test:unit -- --run` 通过）

## 3. 后端评测与自进化默认启用

- [x] 3.1 从 `app/core/config.py` 删除 `EVAL_PLATFORM_ENABLED` 和 `EVOLUTION_ENABLED` 字段，并更新相关配置测试（验证：`rg EVAL_PLATFORM_ENABLED app/core/config.py tests` 无生产代码残留；配置测试断言字段已移除）
- [x] 3.2 调整 `app/main.py` 无条件初始化评测/自进化服务、无条件注册 `/api/eval` 与 `/api/evolution` 路由；保留 `ONLINE_BADCASE_ENABLED` 与自进化调度 cron 子配置（验证：无 enable 配置启动后路由可访问）
- [x] 3.3 删除 `app/routers/eval.py` 和 `app/routers/evolution.py` 中基于 enable 配置的 403 拒绝逻辑和 enabled 状态字段，状态接口改为默认可用或权限状态（验证：管理员调用接口不返回“未启用”）
- [x] 3.4 删除 `app/services/eval/runner_service.py` 与 `app/services/evolution/trigger_service.py` 中 `EVOLUTION_ENABLED` 短路判断（验证：`rg EVOLUTION_ENABLED app/services` 无命中）
- [x] 3.5 更新后端权限测试，覆盖普通用户调用评测/自进化 API 返回 403、管理员在无 enable 配置时可正常访问（验证：`pytest tests/test_eval_platform.py tests/test_evolution_models.py tests/test_evolution_governance.py` 通过）

## 4. 配置与文档清理

- [x] 4.1 从 `.env`、`.env.example`、Docker/部署模板和 README/guide 文档中删除或改写四个废弃开关引用（验证：`rg VITE_EVAL_PLATFORM_ENABLED|VITE_EVOLUTION_ENABLED|EVAL_PLATFORM_ENABLED|EVOLUTION_ENABLED . --glob '!node_modules/**' --glob '!*.log'` 无新增或仅保留明确历史说明）
- [x] 4.2 更新 `tests/test_eval_platform.py` 默认关闭断言、`tests/test_evolution_models.py` 默认关闭断言和 `tests/test_evolution_governance.py` 的 enable mock（验证：对应测试通过且不再断言默认关闭）
- [x] 4.3 更新 `docs/evaluation/agent-evaluation-platform-usage-and-gaps.md` 和 `docs/self-evolution-guide.md` 中依赖 enable 开关的启动或测试说明（验证：文档扫描无开启开关步骤）

## 5. 回归验收

- [x] 5.1 运行前端类型检查和单元测试（验证：`cd frontend && npm run type-check && npm run test:unit` 返回 0）
- [x] 5.2 运行后端相关测试（验证：`pytest tests/test_eval_platform.py tests/test_eval_acceptance.py tests/test_evolution_models.py tests/test_evolution_governance.py` 返回 0）
- [x] 5.3 用管理员和普通用户角色走查：三个充值入口、AI 研究第二位置、管理员可见评测/自进化/系统管理/配置/缓存、普通用户无管理入口且直接 URL 被拦截（验证：走查清单全部通过）
