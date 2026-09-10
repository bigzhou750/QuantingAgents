# model-runtime-governance Specification

## Purpose

确保普通用户不能配置或修改大模型供应商、API Key 和模型参数，运行时模型由后端配置决定并固定采用 DeepSeek。

## Requirements

### Requirement: 普通用户不得看到或修改大模型配置

系统 SHALL 不对匿名用户和普通用户展示大模型供应商选择、API Key 输入、模型参数编辑或默认模型切换控件。普通用户的分析流程 SHALL 使用后端已配置的默认 DeepSeek 模型，不得要求用户提供任何模型凭据。

#### Scenario: 匿名用户访问未完成配置的系统
- **WHEN** 匿名用户首次访问系统且后端缺少必要模型配置
- **THEN** 系统不得显示要求用户填写大模型供应商或 API Key 的向导
- **AND** 系统应显示受控的部署配置错误信息或引导联系管理员

#### Scenario: 普通用户打开分析页面
- **WHEN** 普通用户打开单股分析或批量分析页面
- **THEN** 页面不得显示大模型供应商选择、API Key 输入或可编辑的快速/深度模型配置
- **AND** 分析任务使用后端配置的 DeepSeek 默认模型

#### Scenario: 管理员管理后端模型配置
- **WHEN** 管理员打开配置管理页面
- **THEN** 管理员可以查看和维护后端模型配置
- **AND** 系统不将 API Key 明文返回给浏览器，仅返回已配置状态或脱敏值

### Requirement: 运行时模型固定采用后端 DeepSeek 配置

生产运行时 SHALL 从后端配置或环境配置读取 DeepSeek 供应商、API Key 和模型名，SHALL NOT 使用前端提交的供应商或密钥。发布环境 SHALL 仅启用 DeepSeek 作为默认运行模型，其他供应商不得在默认发布配置中启用。

#### Scenario: 生产环境仅配置 DeepSeek
- **WHEN** 生产环境配置了有效的 `DEEPSEEK_API_KEY` 并启用 DeepSeek
- **THEN** 快速分析使用 `deepseek-chat`，深度分析使用 `deepseek-reasoner`
- **AND** 所有分析请求均使用后端配置的 DeepSeek 凭据

#### Scenario: 生产环境缺少 DeepSeek 配置
- **WHEN** 生产环境未配置有效的 DeepSeek 凭据
- **THEN** 系统不得让用户在前端填写凭据
- **AND** 配置验证应明确报告 DeepSeek 配置缺失

#### Scenario: 浏览器提交自定义供应商
- **WHEN** 普通用户尝试通过前端请求提交非后端配置的模型供应商或 API Key
- **THEN** 系统 SHALL 拒绝该请求或忽略前端模型凭据
- **AND** 请求不得触发任何非 DeepSeek 的模型调用

### Requirement: 前端不得保存或泄露模型密钥

浏览器端 SHALL NOT 将 API Key 写入 `localStorage`、请求分析接口或打印到控制台。配置相关接口返回的密钥 SHALL 始终为脱敏值或状态标识。

#### Scenario: 浏览器控制台检查
- **WHEN** 用户执行任意登录、配置或分析操作
- **THEN** 浏览器控制台不得输出包含完整或可拼接的模型 API Key 的内容

#### Scenario: 分析网络请求检查
- **WHEN** 前端发起分析任务
- **THEN** 请求体不得包含模型 API Key、供应商密钥或自定义模型端点凭据

### Requirement: 所有新闻 Agent 路径遵循同一模型配置

新闻结构化分析 SHALL 使用后端配置的 DeepSeek 模型和密钥，不得绕过统一模型配置直接调用其他供应商。模型不可用时 SHALL 返回可识别的规则降级结果，不得因缺少其他供应商密钥直接返回 500。

#### Scenario: 新闻分析使用 DeepSeek
- **WHEN** 用户提交新闻分析请求且 DeepSeek 配置有效
- **THEN** 新闻 Agent 使用 `deepseek-chat` 调用后端模型
- **AND** 请求不读取或要求 DashScope API Key

#### Scenario: 新闻分析缺少 DeepSeek 密钥
- **WHEN** 用户提交新闻分析请求但 DeepSeek 密钥不可用
- **THEN** 系统返回结构化的规则降级结果
- **AND** 不因 DashScope 或其他供应商缺少密钥而返回内部 500 错误
