## Purpose

本能力用于把新闻关注、影响分析、告警、观察任务和事后复盘连接成闭环，让新闻研究不止停留在一次性结论，而能持续跟踪和校验。

## ADDED Requirements

### Requirement: Holdings impact analysis must load automatically
系统 MUST 在用户进入持仓新闻影响页面时自动加载最新可用分析，并在结果过期或缺失时自动触发后台刷新；手动“重新分析”只作为补充入口。

#### Scenario: Open holdings impact page
- **WHEN** 用户进入持仓新闻影响分析页面
- **THEN** 系统 SHALL 展示最近一次有效分析或自动启动刷新，并显示刷新状态

#### Scenario: Cached analysis is stale
- **WHEN** 最近分析结果超过配置的新鲜度窗口
- **THEN** 系统 SHALL 后台重新分析并在完成后更新页面

### Requirement: Holdings impact must provide a multidimensional scorecard
系统 MUST 为每个受影响持仓提供多维指标，而不是只提供低中高等级；指标至少包括方向、强度、暴露度、新闻数量、新鲜度、证据质量、市场确认、风险类别和待验证指标。

#### Scenario: Render holding impact scorecard
- **WHEN** 系统展示某个持仓的新闻影响
- **THEN** 页面 SHALL 展示该持仓的多维评分、影响路径、关键新闻、证据强弱和后续观察点

#### Scenario: News coverage is weak
- **WHEN** 个股直接新闻不足但存在行业、概念或宏观相关新闻
- **THEN** 系统 SHALL 使用间接新闻生成降级分析，并清楚标注直接覆盖不足

### Requirement: News events must create follow-up observation tasks
系统 MUST 允许用户从新闻分析结果生成观察任务，任务 SHALL 包含观察目标、验证指标、检查时间、关联新闻、关联持仓和完成状态。

#### Scenario: Create an observation task
- **WHEN** 用户从新闻影响分析中点击生成观察任务
- **THEN** 系统 SHALL 创建可追踪任务，并关联原新闻事件、影响分析和相关持仓

#### Scenario: Review observation tasks
- **WHEN** 用户查看新闻研究闭环
- **THEN** 系统 SHALL 展示待观察、已确认、已失效和已复盘的任务状态

### Requirement: Alerts must support confirmation and review
系统 MUST 允许用户对新闻告警进行确认、忽略、转为观察任务或标记为已复盘，并保留用户动作、时间和备注。

#### Scenario: Confirm an alert
- **WHEN** 用户确认某条新闻告警值得跟踪
- **THEN** 系统 SHALL 将告警状态更新为已确认，并允许创建观察任务

#### Scenario: Ignore an alert
- **WHEN** 用户认为告警噪声过高并忽略
- **THEN** 系统 SHALL 记录忽略原因，并用于后续告警去重或阈值优化

### Requirement: The system must support post-event review
系统 MUST 支持在新闻发生后按 1 日、3 日、7 日或可配置窗口复盘价格、成交量、资金流、公告和行业数据是否验证原分析。

#### Scenario: Review an event after the observation window
- **WHEN** 观察窗口到期
- **THEN** 系统 SHALL 汇总新闻后的市场表现、指标变化、原判断命中情况和复盘备注

#### Scenario: Evidence contradicts the original analysis
- **WHEN** 后续数据与原分析方向明显不一致
- **THEN** 系统 SHALL 标记为未验证或反向验证，并保留原因供后续策略改进

### Requirement: Closed-loop metrics must be visible
系统 MUST 展示新闻研究闭环的运行指标，包括新闻覆盖率、分析成功率、告警命中率、观察任务完成率、复盘验证率和噪声率。

#### Scenario: Inspect closed-loop dashboard
- **WHEN** 用户打开新闻闭环概览
- **THEN** 系统 SHALL 展示上述指标及其最近更新时间
