## Purpose

本能力用于把个人投资助手从“已有页面”变成“新手可顺畅使用”的工作流。系统 SHALL 提供默认模板、任务向导、结果解释、观察入口和复盘入口，使用户能更快完成首次画像配置、策略筛选和策略体检。

## ADDED Requirements

### Requirement: First-time users must see guided investment assistant entry points
系统 MUST 在个人投资助手首页或相关入口提供明显的新手引导、默认模板或起步建议，帮助用户快速开始配置画像和策略。

#### Scenario: Open investment assistant for the first time
- **WHEN** 用户首次进入个人投资助手
- **THEN** 系统 SHALL 展示可直接使用的起步模板或引导文案，而不是空白页面

#### Scenario: User chooses a starter template
- **WHEN** 用户选择一个默认画像或策略模板
- **THEN** 系统 SHALL 预填合适的字段并允许用户继续编辑

### Requirement: Beginner strategy selection must be guided and explainable
系统 MUST 在用户不知道如何选策略时提供策略选择向导，帮助用户根据风险偏好、交易风格、资金区间、操作频率和目标市场缩小策略范围。向导 MUST 输出策略类型建议、适用场景和证据层级，而不是直接输出荐股结论。

#### Scenario: User asks which strategy to start with
- **WHEN** 用户首次进入策略选择向导并未指定具体策略
- **THEN** 系统 SHALL 根据画像与偏好给出可理解的策略类型建议

#### Scenario: Strategy suggestion is shown
- **WHEN** 系统展示策略选择结果
- **THEN** 系统 SHALL 说明该策略适合什么人、适合什么市场、当前证据强弱以及主要失效条件

### Requirement: Strategy tasks must use a guided flow
系统 MUST 为策略选股和策略体检提供明确的任务发起路径，允许用户先选择策略，再确认是否带入画像上下文和关键参数。

#### Scenario: Start a screening task
- **WHEN** 用户发起策略选股
- **THEN** 系统 SHALL 让用户明确确认所选策略和本次任务参数后再执行

#### Scenario: Start a checkup task
- **WHEN** 用户发起策略体检
- **THEN** 系统 SHALL 显示该策略的适配对象和本次体检的解释目标

#### Scenario: Start a validation task
- **WHEN** 用户希望验证策略在当前市场是否仍有研究价值
- **THEN** 系统 SHALL 引导用户进入证据查看、历史回测或风险拆解路径，而不是直接宣称收益结果

### Requirement: Results must explain why and what next
系统 MUST 在选股和体检结果页突出展示入选原因、主要风险、与用户画像的冲突点以及下一步可执行动作。

#### Scenario: Screening result is shown
- **WHEN** 选股任务完成
- **THEN** 系统 SHALL 展示候选标的的命中原因、风险提示、画像冲突和后续操作入口

#### Scenario: Checkup result is shown
- **WHEN** 体检任务完成
- **THEN** 系统 SHALL 展示适配度结论、关键指标、风险提示和是否适合当前市场的解释

### Requirement: Reliability must be presented as evidence, not promise
系统 MUST 将策略可靠性展示为可复核证据分层，包括历史回测、风险拆解、当前市场适配和证据新鲜度。系统 MUST NOT 声称策略能够保证盈利。

#### Scenario: User checks whether a strategy can make money
- **WHEN** 用户询问策略是否“能赚钱”
- **THEN** 系统 SHALL 返回证据、风险和适配度说明，而不是收益保证

#### Scenario: User inspects strategy evidence
- **WHEN** 用户查看某策略的验证结果
- **THEN** 系统 SHALL 展示可复核来源、证据层级和当前结论边界

### Requirement: Users must be able to move candidates into follow-up workflows
系统 MUST 提供观察、复盘或继续研究的入口，使用户能够把候选结果从一次性输出转化为持续跟踪对象。

#### Scenario: Add candidate to watchlist
- **WHEN** 用户在结果页选择某个候选标的进入观察
- **THEN** 系统 SHALL 将其加入可继续跟踪的列表或入口

#### Scenario: Open a recap from a prior result
- **WHEN** 用户从历史任务进入复盘
- **THEN** 系统 SHALL 定位到对应结果并展示上一次的分析上下文

### Requirement: User-facing terminology must remain non-advisory
系统 MUST 在个人投资助手的新手引导、结果页和任务入口中持续使用研究、筛选、观察、体检和复盘等表述，MUST NOT 将候选结果包装成买入或卖出建议。

#### Scenario: Result copy is rendered
- **WHEN** 系统渲染选股或体检结果文案
- **THEN** 文案 SHALL 保持非荐股措辞，并保留风险提示

#### Scenario: Guided action label is shown
- **WHEN** 页面提供后续操作按钮
- **THEN** 按钮文案 SHALL 反映研究或跟踪动作，而不是直接交易建议
