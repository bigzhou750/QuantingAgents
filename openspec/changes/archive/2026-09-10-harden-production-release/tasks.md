## 1. 基线与构建一致性

- [x] 1.1 记录当前工作区基线：`HEAD=dbfc60d`，工作区仅新增本 change，`brand-productize-zhitouagent` 已提交；实施过程中不覆盖既有用户修改（Spec: `deployment/release-hardening`；验证：`git status --short` 对比基线）
- [x] 1.2 修复 `Dockerfile.backend` 中不存在的 `zhitouagent` 包复制路径，同步 `pyproject.toml` 的包发现规则和 CLI 入口（Spec: `deployment/release-hardening`；验证：干净环境执行后端镜像构建成功，且 `pip install .` 后 `python -c "import tradingagents"` 成功）
- [x] 1.3 移除后端镜像内复制 `.env.docker` 为运行 `.env` 的行为，改为运行期显式注入环境变量（Spec: `deployment/release-hardening`；验证：镜像文件系统不含 `.env.docker` 或固定生产凭据）
- [x] 1.4 增加或恢复后端构建自检，覆盖包路径、入口点、必需模块可导入（Spec: `deployment/release-hardening`；验证：构建自检命令返回 0）

## 2. 模型运行治理

- [x] 2.1 移除 `App.vue` 对配置向导的全局挂载和自动弹出逻辑，匿名用户和普通用户不再看到配置向导（Spec: `model-runtime-governance`；验证：前端测试断言匿名访问时无向导弹窗）
- [x] 2.2 从发布前端移除或停用 `ConfigWizard.vue` 的大模型供应商、API Key、模型名表单（Spec: `model-runtime-governance`；验证：前端源码和构建产物扫描无该表单）
- [x] 2.3 删除 `App.vue` 等位置对向导数据的 `console.log`，确保任何前端日志不包含模型 API Key（Spec: `model-runtime-governance`；验证：源码扫描和浏览器控制台检查无密钥输出）
- [x] 2.4 普通用户分析页隐藏 `ModelConfig` / `DeepModelSelector` 等可编辑模型配置，只使用后端默认模型（Spec: `model-runtime-governance`；验证：普通用户角色前端测试断言不渲染模型配置控件）
- [x] 2.5 将快速分析和深度分析默认模型固定为 `deepseek-chat` / `deepseek-reasoner`，生产配置仅启用 DeepSeek（Spec: `model-runtime-governance`；验证：配置和测试断言默认模型为 DeepSeek，生产模板无其他默认启用供应商）
- [x] 2.6 确保分析请求体不包含模型 API Key、供应商密钥或自定义端点凭据，并添加接口层校验（Spec: `model-runtime-governance`；验证：请求测试断言请求体中无密钥字段）
- [x] 2.7 更新配置验证与启动校验，生产环境缺失 DeepSeek 配置时明确报错且不引导前端填写凭据（Spec: `model-runtime-governance`；验证：无 `DEEPSEEK_API_KEY` 时启动校验返回明确错误）
- [x] 2.8 修复新闻关注 Agent 绕过统一配置直连 DashScope 的问题，改为后端 DeepSeek 配置并保留规则降级（Spec: `model-runtime-governance`；验证：`pytest tests/test_news_intelligence.py` 通过）

## 3. 默认账号与管理员权限

- [x] 3.1 删除登录页 `admin / admin123` 和“开源版使用默认账号”提示（Spec: `admin-access-hardening`；验证：登录页测试断言无默认账号文案）
- [x] 3.2 移除后端启动时固定密码自动创建管理员逻辑，未提供初始化凭据时不得创建管理员（Spec: `admin-access-hardening`；验证：无初始化环境变量启动后，数据库不存在默认管理员）
- [x] 3.3 调整管理员初始化命令/服务，要求显式密码或一次性令牌，且日志不输出明文密码（Spec: `admin-access-hardening`；验证：初始化测试断言未打印密码）
- [x] 3.4 为 `/settings/config`、`/settings/database`、`/settings/logs`、`/settings/system-logs`、`/settings/sync`、`/settings/scheduler` 等路由补充 `requiresAdmin`（Spec: `admin-access-hardening`；验证：普通用户直接访问这些 URL 被前端守卫拦截）
- [x] 3.5 设置页按管理员状态渲染管理 tab，`/settings?tab=config`、`?tab=database` 等普通用户访问不展示管理内容（Spec: `admin-access-hardening`；验证：普通用户设置页测试断言管理卡片不可见）
- [x] 3.6 补充后端权限测试，普通用户直接调用管理员配置 API 返回 403 且不修改数据（Spec: `admin-access-hardening`；验证：`pytest` 权限测试通过）
- [x] 3.7 生产环境显式配置注册开放策略，登录页注册入口与实际配置一致（Spec: `deployment/release-hardening`；验证：生产配置测试断言注册开关显式生效）

## 4. 生产部署安全

- [x] 4.1 移除 Docker Compose、部署模板和 `.env.docker` 中的固定 MongoDB/Redis/JWT/CSRF 凭据，改用环境变量或 Secrets（Spec: `deployment/release-hardening`；验证：发布扫描对生产部署文件无固定凭据命中）
- [x] 4.2 更新 `deploy/setup.sh` 为缺失的 JWT/CSRF/数据库密码生成随机值，缺少必需密钥时中止部署（Spec: `deployment/release-hardening`；验证：全新环境执行 setup 生成无固定密码的 `.env`）
- [x] 4.3 生产模板显式配置 `ALLOWED_ORIGINS` 和 `ALLOWED_HOSTS`，移除 `CORS_ORIGINS=*` 和默认 `*`（Spec: `deployment/release-hardening`；验证：配置测试断言生产环境无通配 CORS/Host）
- [x] 4.4 统一后端实际读取的 `ALLOWED_ORIGINS` 配置，避免只写 `CORS_ORIGINS` 但不生效（Spec: `deployment/release-hardening`；验证：配置单元测试断言启动值来自 `ALLOWED_ORIGINS`）
- [x] 4.5 更新生产部署文档，要求轮换出现在本地 `.env` 或历史构建中的真实 DeepSeek Key，并说明 `.env` 排除规则（Spec: `deployment/release-hardening`；验证：部署文档脱敏扫描通过）

## 5. 发布包与扫描门禁

- [x] 5.1 调整 `scripts/validation/release_scan.py`，跳过基线扫描 JSON、许可证/归属文件和允许的内部包名路径（Spec: `deployment/release-hardening`；验证：`python scripts/validation/release_scan.py` 对测试发布树返回 0）
- [x] 5.2 定义正式发布树排除清单：真实 `.env`、API Key、日志、缓存、dump、report、`docs/release/brand-migration-baseline-scan.json`、未交付的 Streamlit 源码（Spec: `deployment/release-hardening`；验证：对发布包执行 `tar -tf` 或扫描，排除项不在包内）
- [x] 5.3 清理或 allowlist README、部署文档和发布入口中的旧品牌、旧邮箱、旧仓库链接（Spec: `deployment/release-hardening`；验证：正式发布树发布扫描禁止项为零）
- [x] 5.4 扩展 `tests/test_release_scan.py`，覆盖基线文件跳过、许可证 allowlist、内部包名 allowlist 和真实密钥失败场景（Spec: `deployment/release-hardening`；验证：`pytest tests/test_release_scan.py` 通过）
- [x] 5.5 执行完整验收：前端类型检查、前端生产构建、后端测试、认证权限测试、核心分析回归、后端镜像构建、发布扫描（Spec: `deployment/release-hardening`；验证：所有命令返回 0 并记录结果）
- [x] 5.6 用匿名、普通用户、管理员三种角色走查公开页、登录、分析、设置和管理员配置主流程（Spec: `admin-access-hardening`；验证：走查清单覆盖三种角色且无越权路径）
