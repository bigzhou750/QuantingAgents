## ADDED Requirements

### Requirement: Admin management navigation must be role-based and independent of feature flags

Agent 评测、自进化、系统管理一级菜单，以及设置中的配置管理和缓存管理 SHALL 只对管理员显示。这些入口的可见性 SHALL 只由当前用户的管理员角色决定，SHALL NOT 依赖 `VITE_EVAL_PLATFORM_ENABLED`、`VITE_EVOLUTION_ENABLED` 或其他 feature enable 环境配置。

#### Scenario: Admin sees all management entries without env flags
- **WHEN** 当前用户是管理员且未配置评测/自进化 feature enable 环境变量
- **THEN** 侧边栏仍显示 Agent 评测和自进化菜单
- **AND** 侧边栏仍显示系统管理、配置管理和缓存管理入口

#### Scenario: Admin sees all management entries when env flags are false
- **WHEN** 当前用户是管理员且评测/自进化 enable 环境变量为 `false`
- **THEN** Agent 评测和自进化菜单仍然显示
- **AND** 点击后仍可进入对应工作台

#### Scenario: Non-admin never sees management entries
- **WHEN** 当前用户不是管理员，即使评测/自进化 enable 环境变量为 `true`
- **THEN** Agent 评测、自进化、系统管理、配置管理和缓存管理入口 SHALL NOT 出现在侧边栏或设置页

### Requirement: Non-admin route access to management URLs must remain blocked

普通用户直接访问系统管理、配置管理、缓存管理、Agent 评测或自进化 URL SHALL 被前端守卫拦截；即使绕过前端，后端对应接口 SHALL 仍返回 403。

#### Scenario: Non-admin tries to open a management URL directly
- **WHEN** 普通用户直接访问 `/settings/config`、`/settings/cache`、`/evaluation/dashboard` 或 `/evolution/proposals`
- **THEN** 前端将用户重定向到非管理页面并提示无权限

#### Scenario: Non-admin calls a management API directly
- **WHEN** 普通用户携带登录态直接调用评测、自进化或管理层 API
- **THEN** 后端 SHALL 返回 403
- **AND** 请求 SHALL NOT 执行受保护操作

### Requirement: Recharge entry must not alter admin management visibility

增加充值入口 SHALL NOT 改变普通用户的非管理员菜单内容，也不得让普通用户在任一充值入口之外看到受保护管理功能。

#### Scenario: Recharge menu appears without exposing management entries
- **WHEN** 普通用户看到侧边栏中的算力充值入口
- **THEN** 该用户仍看不到 Agent 评测、自进化、系统管理、配置管理和缓存管理入口
