## Why

当前项目仍存在上线阻断项：普通用户可通过首次配置向导填写大模型供应商与 API Key，登录页仍展示固定管理员账号，生产 Compose 仍包含固定数据库密码和 JWT 密钥，Dockerfile 引用了不存在的 `zhitouagent/` 目录，发布扫描也未通过。这些问题会导致构建失败、凭据泄露和权限越权风险，必须在正式上线前关闭。

## Scope

本 change 只处理上线前必须关闭的安全、权限、构建和发布门禁风险，不调整投资分析算法、Agent 决策逻辑、数据源协议或既有业务 API 的字段契约。

## Non-Goals

- 不重写 `tradingagents/` 核心算法或第三方适配器。
- 不改变已有分析、评测、自进化能力的业务行为。
- 不在本 change 中决定正式域名、HTTPS 证书签发方式或支付服务商。
- 不删除法律要求保留的许可证、版权和第三方归属信息。

## What Changes

- **BREAKING** 移除普通用户可见的大模型配置入口：首次配置向导不再让用户选择供应商、填写 API Key 或模型名，`App.vue` 不再全局自动弹出该向导。
- 运行时大模型统一由后端配置决定，并固定采用 DeepSeek：前端不再保存或提交 LLM API Key，默认模型收敛为 `deepseek-chat` / `deepseek-reasoner`。
- 删除登录页展示的默认管理员账号密码，移除后端首次启动时使用固定密码自动创建管理员的行为，管理员初始凭据改为环境变量或一次性引导。
- 补齐管理员页面前端权限：`/settings/config`、`/settings/database`、`/settings/logs`、`/settings/system-logs`、`/settings/sync`、`/settings/scheduler` 等路由和设置页 tab 均须在普通用户侧不可达。
- 生产配置不再硬编码 MongoDB/Redis 密码、JWT/CSRF 密钥和通配 CORS；`ALLOWED_ORIGINS`、`ALLOWED_HOSTS` 必须显式配置。
- 修复 Docker 构建路径不一致，统一 `pyproject.toml`、Dockerfile 与 Python 包目录关系，确保后端镜像可构建、可安装。
- 从发布包中排除真实 `.env`、真实密钥、旧 Streamlit 应用、运行时报告、缓存、dump 和基线扫描 JSON；发布扫描需通过验收门禁。
- 上线前明确注册开放策略、真实 API Key 轮换和旧品牌残留清理，避免公开注册消耗生产额度或发布包携带敏感数据。

## Capabilities

### New Capabilities

- `model-runtime-governance`: 定义普通用户不得配置或修改大模型供应商/API Key，运行时模型由后端配置决定并固定使用 DeepSeek 的契约。
- `admin-access-hardening`: 定义管理员配置页面、设置 tab 和默认管理员引导的前后端权限边界。
- `deployment/release-hardening`: 定义生产部署密钥、CORS/Host 约束、构建可复现性、发布包排除规则和发布扫描门禁。

### Modified Capabilities

无。本 change 不修改 `openspec/specs/agent-evaluation-platform` 的既有契约。

## Impact

- **Frontend**: 影响 `frontend/src/App.vue`、`ConfigWizard.vue`、`Login.vue`、`Settings/index.vue`、`router/index.ts` 及相关设置组件。
- **Backend**: 影响 `app/main.py`、`app/services/user_service.py`、`app/core/startup_validator.py`、配置管理路由和运行时模型默认值。
- **Build/Deployment**: 影响 `Dockerfile.backend`、`pyproject.toml`、Docker Compose 文件、`.env.docker`、部署模板、`.dockerignore` 和发布扫描脚本。
- **Compatibility**: 保留旧环境变量读取兼容，但新部署使用 `ZHITOUAGENT_*` 或既定新键；外部调用方必须继续使用既有 API 契约。

## Acceptance Criteria

- 匿名用户和普通用户无法在任何前端页面填写或提交大模型供应商、API Key、模型名。
- 登录页不展示任何默认账号密码，后端不会用固定密码自动创建管理员。
- 普通用户直接访问管理员 URL 或设置 tab 会被前端守卫拦截，后端对应 API 仍保持管理员校验。
- 生产 Compose 和环境模板不包含固定数据库密码、固定 JWT/CSRF 密钥或通配 CORS/Host。
- `Dockerfile.backend` 构建成功，后端镜像内包名、入口点与 `pyproject.toml` 一致。
- `scripts/validation/release_scan.py` 在正式发布树上通过，禁止项为零，允许项有明确清单。
- 后端测试、前端类型检查和生产构建均通过。
