## Purpose

本能力用于保证新闻关注模块拥有可用、可解释、可降级的新闻供给，避免单一来源失败、近期缓存为空或同步任务未运行时直接让用户看到空页面。

## ADDED Requirements

### Requirement: The system must aggregate news from multiple source tiers
系统 MUST 将新闻来源按个股新闻、市场新闻、公告、行业政策、宏观事件和兜底搜索进行分层聚合，并在返回结果中标明每条新闻的来源、采集时间、发布时间和关联标的。

#### Scenario: Fetch related news for a watched stock
- **WHEN** 用户查看某个已关注股票的相关新闻
- **THEN** 系统 SHALL 返回来自至少一个可用来源的新闻列表，并标明来源层级、数据源名称和发布时间

#### Scenario: Fetch market news with no watched items
- **WHEN** 用户尚未关注任何股票或新闻但进入新闻工作台
- **THEN** 系统 SHALL 尝试返回市场新闻、热门股票新闻或兜底新闻，而不是只展示空白列表

### Requirement: The system must apply deterministic fallback when news is sparse
系统 MUST 在新闻不足时按明确顺序降级查询，至少支持扩大时间窗口、查询关联行业、查询自选或持仓标的、查询默认热门标的和调用兜底搜索来源。

#### Scenario: Recent news is empty
- **WHEN** 近 72 小时没有命中相关新闻
- **THEN** 系统 SHALL 自动扩大到 7 天、30 天或可配置窗口，并在响应中说明使用了扩大窗口

#### Scenario: Direct stock news is empty
- **WHEN** 个股新闻源没有返回指定标的新闻
- **THEN** 系统 SHALL 查询该标的所属行业、概念、公告或默认兜底源，并标记结果为间接覆盖

#### Scenario: All external sources fail
- **WHEN** 所有外部新闻来源请求失败
- **THEN** 系统 SHALL 返回可诊断的失败摘要，包括失败来源、最近成功时间和建议的恢复动作

### Requirement: Source coverage must be observable
系统 MUST 为新闻工作台和调试接口提供来源覆盖信息，使用户或管理员能看出新闻少是因为确实缺少事件、来源失败、权限缺失、限流还是缓存过期。

#### Scenario: Inspect source coverage
- **WHEN** 工作台或调试面板展示新闻结果
- **THEN** 系统 SHALL 展示总条数、直接命中条数、间接命中条数、来源数量、最近成功来源和数据新鲜度

#### Scenario: A source returns no data
- **WHEN** 某个新闻源返回空数据
- **THEN** 系统 SHALL 记录该来源为空的时间、请求范围和是否触发了后续降级

### Requirement: News source failures must not be silently treated as success
系统 MUST 区分“成功但无新闻”和“来源异常导致无新闻”，不得把解析异常、网络异常、鉴权失败或限流失败记为正常成功。

#### Scenario: Provider parser fails
- **WHEN** 新闻源适配器发生解析异常
- **THEN** 系统 SHALL 记录失败原因并触发下一级来源，而不是把结果计为成功 0 条

#### Scenario: Provider succeeds with empty result
- **WHEN** 新闻源正常响应但没有匹配新闻
- **THEN** 系统 SHALL 将该来源状态标记为 empty，并继续执行配置允许的降级查询
