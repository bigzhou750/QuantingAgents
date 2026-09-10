## Purpose

确保生产构建、部署配置和发布包可复现、不包含固定凭据或敏感文件，并通过发布扫描门禁。

## ADDED Requirements

### Requirement: Docker 构建与 Python 包结构必须一致

后端 Docker 构建引用的包目录 SHALL 存在且与 `pyproject.toml` 的包发现规则一致。后端镜像 SHALL 可在干净环境完成构建、安装和启动。

#### Scenario: 干净环境构建后端镜像
- **WHEN** 在干净 Docker 环境中执行后端镜像构建
- **THEN** 构建成功
- **AND** 镜像内可导入运行所需的核心 Python 包

#### Scenario: 包名或目录被修改
- **WHEN** 核心 Python 包目录或包名发生变化
- **THEN** Dockerfile、`pyproject.toml`、项目脚本入口和导入关系必须同步更新
- **AND** 构建验证必须失败而不是生成缺失模块的镜像

### Requirement: 生产部署不得硬编码固定凭据

生产 Compose 和环境模板 SHALL NOT 硬编码 MongoDB/Redis 密码、JWT 密钥、CSRF 密钥或真实 API Key。上述值 SHALL 来自部署环境变量、Secrets 或生成的一次性值。

#### Scenario: 生产 Compose 凭据检查
- **WHEN** 检查生产 Compose 和部署模板
- **THEN** 不得发现固定数据库密码、固定 JWT/CSRF 密钥或真实 API Key

#### Scenario: 生产环境启动
- **WHEN** 生产环境使用真实环境变量启动
- **THEN** 数据库、缓存和认证使用部署方提供的值
- **AND** 启动日志不得打印明文密钥

### Requirement: 生产 CORS 与 Host 必须显式收紧

生产环境 SHALL 配置明确的 `ALLOWED_ORIGINS` 和 `ALLOWED_HOSTS`，SHALL NOT 使用通配符。同源部署不得依赖通配 CORS。

#### Scenario: 正式域名访问
- **WHEN** 用户从正式域名访问生产系统
- **THEN** 请求被允许且响应包含正确的安全头

#### Scenario: 非预期 Host 或 Origin 访问
- **WHEN** 请求使用非白名单 Host 或 Origin
- **THEN** 系统拒绝请求或浏览器阻止跨域响应

### Requirement: 发布包必须排除敏感与非交付文件

正式发布包 SHALL 排除真实 `.env`、真实 API Key、生产连接串、日志、缓存、dump、运行时报告、内部调试文档和基线扫描 JSON。若旧 Streamlit 应用不参与生产交付，其源码 SHALL 不出现在发布包中。

#### Scenario: 发布包敏感文件扫描
- **WHEN** 对正式发布树执行发布扫描
- **THEN** 不得发现真实密钥、固定生产凭据或敏感数据文件

#### Scenario: 旧 Streamlit 应用未纳入交付
- **WHEN** 生产交付只使用 FastAPI 与 Vue 应用
- **THEN** 旧 Streamlit 页面不得作为可访问入口进入发布包

### Requirement: 发布扫描门禁必须可复现通过

发布扫描 SHALL 在正式发布树上返回通过；允许项 SHALL 有明确且可审计的原因清单。扫描器自身 SHALL 排除基线扫描输出和许可证/归属等允许文件。

#### Scenario: 执行发布扫描
- **WHEN** 在发布前执行 `release_scan`
- **THEN** 禁止项为零
- **AND** 输出包含扫描范围、允许项和审核记录

#### Scenario: 扫描器自身误报基线文件
- **WHEN** 扫描包含历史基线扫描 JSON 的发布树
- **THEN** 基线文件应被排除或标记为允许项
- **AND** 不得导致发布门禁失败

### Requirement: 生产注册策略必须显式配置

生产环境 SHALL 显式配置是否开放注册。若产品不向公众开放注册，注册入口 SHALL 被关闭或仅允许受控账号创建。

#### Scenario: 关闭公开注册
- **WHEN** 生产环境配置关闭公开注册
- **THEN** 登录页不提供注册入口
- **AND** 未授权用户无法自行创建账号

#### Scenario: 开放公开注册
- **WHEN** 生产环境明确配置开放注册
- **THEN** 注册流程遵守配额、风控和用户协议要求
- **AND** 系统记录注册与使用审计信息
