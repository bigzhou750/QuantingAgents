# admin-access-hardening Specification

## Purpose

确保管理员配置页面、设置 tab 和默认管理员引导只能由管理员或受控部署操作访问，普通用户无法通过菜单或直接 URL 越权进入。

## Requirements

### Requirement: 管理员页面必须同时受前端守卫和后端权限保护

配置管理、数据库管理、操作日志、系统日志、多数据源同步、定时任务、计费配置等管理员页面 SHALL 在路由层标记为管理员专用。普通用户直接访问这些 URL 或通过设置 tab 进入时 SHALL 被前端守卫拦截；即使绕过前端，后端 API SHALL 仍返回 403。

#### Scenario: 普通用户直接访问管理员 URL
- **WHEN** 普通用户访问 `/settings/config` 或 `/settings/database` 等管理员 URL
- **THEN** 前端将用户重定向回非管理页面并显示无权限提示

#### Scenario: 普通用户通过设置 tab 尝试进入管理内容
- **WHEN** 普通用户访问 `/settings?tab=config` 或 `/settings?tab=database`
- **THEN** 页面不得渲染配置管理、数据库管理、日志管理或同步管理内容

#### Scenario: 普通用户直接调用管理员 API
- **WHEN** 普通用户携带有效登录态直接调用管理员配置写接口
- **THEN** 后端 SHALL 返回 403
- **AND** 请求不得修改任何系统配置

### Requirement: 登录页不得展示默认管理员凭据

登录页 SHALL NOT 展示任何默认账号、默认密码或“开源版使用默认账号”提示。产品页面不得公开 `admin/admin123` 或类似可登录凭据。

#### Scenario: 登录页内容检查
- **WHEN** 匿名用户打开登录页
- **THEN** 页面不得出现任何用户名和密码组合提示
- **AND** 页面只展示正常的账号登录和注册入口

### Requirement: 管理员初始账号必须使用受控凭据创建

系统首次启动 SHALL NOT 使用固定密码自动创建管理员。管理员初始密码 SHALL 来自部署环境变量、初始化脚本参数或一次性安全引导，且日志 SHALL NOT 输出明文密码。

#### Scenario: 首次启动未提供管理员密码
- **WHEN** 后端首次启动且未配置管理员初始密码环境变量
- **THEN** 系统不得创建固定密码管理员
- **AND** 应记录明确的初始化提示，说明管理员需通过受控方式创建

#### Scenario: 首次启动使用环境变量创建管理员
- **WHEN** 部署方通过环境变量或安全初始化流程提供初始管理员凭据
- **THEN** 系统创建唯一管理员账号并完成首次登录
- **AND** 日志不得输出明文密码

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
