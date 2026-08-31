## Purpose

本能力用于把新闻从标题列表升级为可复核的研究分析对象，让用户能够通过 Agent 理解新闻可能影响的行业、板块、上下游、持仓和后续观察指标。

## ADDED Requirements

### Requirement: Users must be able to analyze a news item or news cluster
系统 MUST 为单条新闻、批量选中新闻和事件聚类提供 Agent 分析入口，分析结果 MUST 保留输入新闻、prompt 版本、生成时间和用户上下文。

#### Scenario: Analyze one news item
- **WHEN** 用户在新闻工作台点击某条新闻的“分析影响”
- **THEN** 系统 SHALL 返回该新闻的事件摘要、影响方向、影响强度、相关行业板块、关联标的和证据说明

#### Scenario: Analyze selected news items
- **WHEN** 用户批量选择多条新闻并执行分析
- **THEN** 系统 SHALL 先聚合同一事件或主题，再输出统一的事件影响分析

### Requirement: Agent analysis must cover market impact dimensions
系统 MUST 要求 Agent 至少分析事件类型、影响方向、短中期时间窗口、直接受益/受损行业、上下游传导、竞品替代、持仓命中、证据强度、市场确认和待验证指标。

#### Scenario: Render structured analysis
- **WHEN** Agent 分析完成
- **THEN** 系统 SHALL 以结构化模块展示事件摘要、影响路径、行业板块、持仓关联、风险类型、时间窗口、证据强度和观察清单

#### Scenario: Identify indirect impact
- **WHEN** 新闻没有直接提到用户持仓但命中其行业、供应链或竞品
- **THEN** 系统 SHALL 标记为间接影响，并解释传导路径

### Requirement: Analysis prompts must be controlled and versioned
系统 MUST 使用受控 prompt 模板生成新闻影响分析，并记录 prompt 版本、输入摘要、模型配置和输出 schema 版本，便于复核和后续迭代。

#### Scenario: Prompt version changes
- **WHEN** 分析 prompt 被调整
- **THEN** 系统 SHALL 将新旧分析结果按 prompt 版本区分，并允许用户查看分析生成依据

#### Scenario: Agent output is incomplete
- **WHEN** Agent 返回内容缺少必需字段或结构化解析失败
- **THEN** 系统 SHALL 返回降级分析结果和失败原因，而不是展示不完整结论

### Requirement: Agent analysis must remain non-advisory
系统 MUST 将 Agent 输出限制为研究解释、风险提示、观察计划和证据说明，MUST NOT 输出买入、卖出、加仓、减仓、目标收益或确定性预测。

#### Scenario: Agent infers a trading action
- **WHEN** Agent 输出包含交易指令或收益承诺
- **THEN** 系统 SHALL 拦截或改写为非交易建议的研究表述，并记录安全处理结果

### Requirement: Analysis results must support reuse by holdings and alerts
系统 MUST 将新闻影响分析结果保存为可复用记录，使持仓影响分析、告警和复盘能够引用同一份事件解释与证据。

#### Scenario: Holdings analysis uses prior event analysis
- **WHEN** 持仓影响分析命中已经分析过的新闻事件
- **THEN** 系统 SHALL 复用已有事件影响结果，并记录复用关系
