# release-origin-governance Specification

## Purpose
为不公开源码的生产发布建立可重复的来源治理和发布包验收机制，清理产品可见的旧项目痕迹与敏感信息，同时集中保留法律要求的第三方许可证、版权和归属记录。

## Requirements

### Requirement: Product release SHALL pass identity and contact scans
发布检查 SHALL 扫描源代码、前端构建产物、Docker 配置、部署模板、公开文档和运行时资源，禁止旧产品品牌、旧项目邮箱、旧项目仓库地址、原项目推广入口或不应公开的上游同步配置进入对外发布包。

#### Scenario: Clean release candidate passes scan
- **WHEN** 对候选发布目录执行发布扫描
- **THEN** 扫描报告显示旧品牌、旧联系方式和旧项目地址为零命中，且报告列出被允许的第三方依赖来源和归属例外

#### Scenario: Scan finds a forbidden product residue
- **WHEN** 构建产物或运行时资源包含旧品牌、旧邮箱或旧项目地址
- **THEN** 发布检查失败并指出文件、行号或资源位置，不能生成“通过”状态

### Requirement: Required third-party notices SHALL be preserved and isolated
发布包 SHALL 保留适用许可证、版权声明、NOTICE 和第三方依赖归属；这些材料 MUST 与产品营销文案、旧项目推广入口和个人支持入口分离，且不得被扫描规则误判为产品身份信息。

#### Scenario: License audit runs
- **WHEN** 对发布包执行许可证审计
- **THEN** 审计能定位第三方组件、适用许可证和必要归属，且不会要求删除法律上必须保留的内容

### Requirement: Sensitive development data SHALL be excluded
发布包 MUST 排除 `.env` 中的真实密钥、生产数据库连接、日志、缓存、dump、用户数据、调试报告和内部路径；模板只能包含脱敏占位符。

#### Scenario: Production package is inspected
- **WHEN** 对 Docker context、前端 dist、后端发布目录和部署压缩包执行敏感信息检查
- **THEN** 不包含真实 API Key、密码、Token、用户数据或生产日志，且服务可以使用模板配置启动

### Requirement: Release verification SHALL cover runtime compatibility
发布验收 SHALL 包含前端构建、后端测试、认证权限测试、核心分析测试、Agent 事件流测试、工具/提示词加载测试和新命名启动检查。

#### Scenario: Verification suite completes
- **WHEN** 执行发布验收命令
- **THEN** 所有必需检查通过，并生成可追溯的检查摘要；任何核心能力回归或品牌泄漏均阻止发布
