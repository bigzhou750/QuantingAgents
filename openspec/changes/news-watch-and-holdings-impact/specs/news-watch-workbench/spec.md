## Purpose

本能力用于让用户一键收集自己关注的股票或新闻，并在同一个工作台里查看最近收集到的研究对象和相关新闻流。

## ADDED Requirements

### Requirement: Users must be able to collect watched stocks and news with one action
系统 MUST 允许用户从股票详情、自选股或新闻列表将股票或新闻条目一键加入关注工作台。

#### Scenario: Collect a stock from stock detail
- **WHEN** 用户在股票详情页点击收集当前股票
- **THEN** 系统 SHALL 将该股票记录到关注工作台，并保留来源页面信息

#### Scenario: Collect a news item from a news list
- **WHEN** 用户在新闻列表点击收集某条新闻
- **THEN** 系统 SHALL 将该新闻记录到关注工作台，并保留新闻来源和发布时间

### Requirement: Collected items must remain traceable
系统 MUST 为每条收集记录保存来源标识、收集时间、关联标的或新闻条目，以及数据来源信息，便于用户回看来源。

#### Scenario: View a collected item
- **WHEN** 用户打开某条收集记录
- **THEN** 系统 SHALL 显示该记录来自哪个页面、哪个标的或新闻、以及何时收集

### Requirement: The workbench must show recent collected items and related news
系统 MUST 提供一个可浏览的工作台，用于查看最近收集的股票、相关新闻和收集状态。

#### Scenario: Open the workbench
- **WHEN** 用户进入关注工作台
- **THEN** 系统 SHALL 展示最近收集的对象及其最新相关新闻或行情入口

#### Scenario: No collected items exist
- **WHEN** 用户尚未收集任何对象
- **THEN** 系统 SHALL 显示空状态和起步引导，而不是报错

### Requirement: User-facing copy must stay research-oriented
系统 MUST 使用关注、收集、研究、观察等表述，MUST NOT 将收集动作包装成买入或卖出建议。

#### Scenario: Collection button is shown
- **WHEN** 页面展示收集按钮
- **THEN** 按钮文案 SHALL 表达研究收集语义，而不是交易语义
