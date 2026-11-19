## Purpose

本能力用于在新闻影响达到用户设定阈值时生成告警记录，并以模拟方式验证短信或微信机器人投递流程。

## ADDED Requirements

### Requirement: Users must be able to configure alert thresholds
系统 MUST 允许用户为新闻影响设置告警阈值，阈值 MUST 基于三档影响等级配置。

#### Scenario: Configure alert threshold
- **WHEN** 用户选择“中等及以上”作为告警阈值
- **THEN** 系统 SHALL 将中等和高等级影响纳入告警条件

#### Scenario: Configure strict alert threshold
- **WHEN** 用户选择“仅高等级”作为告警阈值
- **THEN** 系统 SHALL 只对高等级影响生成告警

#### Scenario: Configure broad alert threshold
- **WHEN** 用户选择“低等级及以上”作为告警阈值
- **THEN** 系统 SHALL 将低、中、高等级影响都纳入告警条件

### Requirement: Alert delivery must be simulated first
系统 MUST 先以模拟方式记录告警投递，不得默认接入真实短信或微信机器人渠道。

#### Scenario: Alert is triggered
- **WHEN** 新闻影响达到用户阈值
- **THEN** 系统 SHALL 生成模拟告警记录，包含目标渠道、触发原因和时间

#### Scenario: Delivery is inspected
- **WHEN** 用户查看告警记录
- **THEN** 系统 SHALL 明确标记该告警为模拟投递，而不是实际外发消息

### Requirement: Alerting must remain traceable
系统 MUST 记录每次告警的触发来源、关联标的、影响等级和投递状态，便于复查和去重。

#### Scenario: Multiple news items trigger alerts
- **WHEN** 同一标的在短时间内触发多次告警
- **THEN** 系统 SHALL 保留告警记录并支持后续去重或聚合

### Requirement: Alerting must remain non-advisory
系统 MUST 只提示风险和研究结果，MUST NOT 把告警包装成交易建议或收益承诺。

#### Scenario: Alert is rendered in UI
- **WHEN** 告警列表展示给用户
- **THEN** 文案 SHALL 明确是研究告警，不是交易信号
