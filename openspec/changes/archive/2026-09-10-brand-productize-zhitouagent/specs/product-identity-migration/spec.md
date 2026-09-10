## Purpose

为智能投研助手建立一致的个人产品身份，使用户界面、运行时标识、部署资源和默认配置对外呈现为 `zhitouagent`，同时保留现有核心 Agent 能力和兼容契约。

## ADDED Requirements

### Requirement: Product identity SHALL be consistent
产品界面、公开文档、CLI 输出、报告元数据和默认配置中的产品名称 SHALL 使用“智能投研助手”或 `zhitouagent`，不得继续使用原项目品牌作为产品身份。

#### Scenario: User views product entry points
- **WHEN** 用户访问登录页、注册页、关于页、主工作台、报告导出结果或 CLI 帮助
- **THEN** 页面或输出显示“智能投研助手”/`zhitouagent`，并显示统一的免责声明和支持联系方式

### Requirement: Runtime identifiers SHALL use the product namespace
运行时生成的 User-Agent、默认缓存/日志标识、容器与服务标识、环境变量和可见错误信息 SHALL 使用 `zhitouagent` 命名；保留核心运行能力所需的旧配置兼容读取时，兼容项不得继续作为新默认值输出。

#### Scenario: New deployment starts with product defaults
- **WHEN** 使用新发布的部署模板启动服务
- **THEN** 新建资源、日志文件、默认路径和请求 User-Agent 使用 `zhitouagent` 标识，且服务健康检查和关键 Agent 流程正常

#### Scenario: Legacy configuration is encountered
- **WHEN** 系统读取带有旧命名的既有配置或数据目录
- **THEN** 系统按迁移规则读取或提示迁移，不能静默丢失配置；新写入值使用 `zhitouagent` 命名

### Requirement: Core Agent behavior SHALL remain compatible
品牌迁移 SHALL 保留投资分析、研究工作台、Agent 运行时、工具调用、提示词能力、认证权限和现有外部 API 的行为兼容性；必要的内部重命名 MUST 提供兼容导入或迁移路径。

#### Scenario: Existing analysis request is executed
- **WHEN** 已认证用户提交单股、批量或自然语言研究任务
- **THEN** 任务仍按原权限和配置执行，能够产出结果、进度事件和风险提示，且接口状态码与响应结构保持兼容

#### Scenario: Runtime tool or prompt is loaded
- **WHEN** Agent 加载内置工具、用户技能、提示词或外部连接器
- **THEN** 加载路径和功能可用，产品输出不暴露旧项目品牌、旧运行时路径或内部来源宣传文案
