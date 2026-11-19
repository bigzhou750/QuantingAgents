## Purpose

本能力用于把近期新闻映射到用户当前持仓，说明哪些持仓被影响、影响方向是什么、证据有多新，而不是直接给出交易结论。

## ADDED Requirements

### Requirement: Users must be able to analyze news impact on current holdings
系统 MUST 提供基于当前持仓的新闻影响分析，能够把近期新闻按持仓、行业或相关标的进行归因和汇总。

#### Scenario: Analyze holdings impact
- **WHEN** 用户对当前持仓执行新闻影响分析
- **THEN** 系统 SHALL 返回受影响的持仓、相关新闻摘要和影响方向

#### Scenario: No holdings are available
- **WHEN** 用户没有可用持仓
- **THEN** 系统 SHALL 明确提示无法进行持仓影响分析，并给出可退化到的新闻观察结果

### Requirement: Impact analysis must include exposure and freshness
系统 MUST 在分析结果中展示相关性、暴露度和新闻新鲜度，让用户知道为什么这条新闻被认为重要。

#### Scenario: A holding is matched to several news items
- **WHEN** 多条新闻命中同一持仓
- **THEN** 系统 SHALL 展示聚合后的影响摘要、优先级和最新发布时间

### Requirement: Impact analysis must expose a three-level severity
系统 MUST 将新闻对持仓的影响分为低、中、高三档，并让后续告警逻辑直接复用该分级结果。

#### Scenario: Analysis result is generated
- **WHEN** 系统完成新闻影响分析
- **THEN** 系统 SHALL 为结果标记三档影响等级之一

#### Scenario: User wants to configure alerts
- **WHEN** 用户选择告警阈值
- **THEN** 系统 SHALL 以三档等级作为配置入口，并允许中等及以上触发告警

#### Scenario: User selects low threshold
- **WHEN** 用户选择低等级作为告警阈值
- **THEN** 系统 SHALL 将低、中、高等级影响都纳入告警条件

### Requirement: Impact analysis must be explainable and non-advisory
系统 MUST 说明影响结论的依据、边界和不确定性，MUST NOT 声称能够保证收益或输出买卖建议。

#### Scenario: User asks whether the news means the holding should be bought or sold
- **WHEN** 用户把分析结果理解为交易建议
- **THEN** 系统 SHALL 只返回研究解释和风险提示，不返回交易指令

### Requirement: Insufficient data must be reported honestly
系统 MUST 在新闻不足、匹配不足或持仓信息不完整时明确标记分析不充分。

#### Scenario: News coverage is sparse
- **WHEN** 可用于分析的新闻很少
- **THEN** 系统 SHALL 将结果标记为证据不足或覆盖不足，而不是强行下结论
