## Purpose

为审核和真实用户建立无需登录即可检查的产品信息、计费、隐私、服务支持和风险披露入口，确保产品定位清晰、联系方式真实且投资分析用途得到明确限制。

## ADDED Requirements

### Requirement: Public product information SHALL be accessible without login
系统 SHALL 提供无需登录即可访问的产品介绍、核心功能、适用用途、联系方式和服务入口；公开页面不得仅显示登录后才能理解的空壳界面。

#### Scenario: Anonymous visitor reviews the product
- **WHEN** 未登录用户访问产品入口或公开产品页
- **THEN** 用户能看到“智能投研助手”的明确定位、主要功能、支持市场、研究用途说明和 `zh75067197@gmail.com` 支持邮箱

### Requirement: Pricing and usage rules SHALL be visible
系统 SHALL 提供公开可访问的价格/套餐、Token 或额度消耗规则、限制、续费/退款说明；实际计费页面与公开说明不一致时 MUST 显示当前生效规则或明确标记尚未开放。

#### Scenario: Anonymous visitor checks pricing
- **WHEN** 未登录用户访问定价或计费说明
- **THEN** 页面显示当前套餐、价格、额度/Token 规则、并发或频率限制，以及联系支持的方式

### Requirement: Privacy and terms SHALL be available at trust boundaries
系统 SHALL 提供隐私政策和服务条款的公开页面，并在注册、登录或首次使用前提供可访问入口；内容 MUST 说明账户数据、研究输入、模型服务、金融数据源、日志、保留期限和用户权利。

#### Scenario: User opens legal documents before registration
- **WHEN** 用户在未登录状态打开注册页或服务条款/隐私政策链接
- **THEN** 文档可正常加载，且不要求先完成注册或提供 API Key

### Requirement: Investment outputs SHALL carry consistent risk disclosure
分析页面、研究工作台、任务结果、报告导出和公开产品页 SHALL 明确说明输出仅用于研究和信息参考，不构成投资、证券、交易或收益承诺；系统 MUST 避免将模型结果描述为保证性建议。

#### Scenario: User receives an analysis result
- **WHEN** 单股分析、筛选、研究对话或报告生成完成
- **THEN** 结果附近显示统一风险提示，并保留数据时间、来源或不确定性说明（在可用时）

### Requirement: Support contact SHALL be consistent
对外支持入口 SHALL 统一使用 `zh75067197@gmail.com`；系统不得在产品页、公开文档、默认客服配置或错误提示中继续显示原项目邮箱。

#### Scenario: User seeks support
- **WHEN** 用户访问关于页、页脚、服务条款、定价页或错误帮助入口
- **THEN** 用户看到同一支持邮箱，且邮件链接可用
