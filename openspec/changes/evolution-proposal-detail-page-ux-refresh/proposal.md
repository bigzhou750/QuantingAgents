## Why

当前自进化提案详情页把生命周期信息、变更原文、验证结果和审批记录并排堆在一起，用户需要自己猜每个 JSON 块和标签的含义，难以快速判断这个提案处于什么状态、为什么触发、以及是否已经具备发布条件。这个问题会直接拖慢审批和排障效率，也会削弱对自进化闭环的可理解性。

## What Changes

- 将提案详情页重组为更清晰的信息层级，突出“概览、变更、验证、审批/发布”四段式结构
- 将触发类型、状态、风险等级、基线版本、候选版本、gate 结果等信息改为可解释文案和状态卡
- 将 `diff` 与 `comparison_result` 从默认 JSON 视图改为结构化摘要 + 可展开原文
- 在审批记录、验证记录或对比数据缺失时显示明确空态与原因，避免出现无意义空白区块
- 将批准、拒绝、启动验证、发布、停止等操作改为状态感知按钮，减少误触
- 保留原始 JSON 和原始事件作为辅助查看入口，而不是默认主视图

## Capabilities

### New Capabilities
- `evolution-proposal-detail-ux`: 提案详情页需要提供可解释的生命周期、变更、验证与审计展示

### Modified Capabilities
- 无

## Impact

- frontend/src/views/Evolution/ProposalDetail.vue
- frontend/src/views/Evolution/Proposals.vue
- frontend/src/api/evolutionClient.ts
- frontend/src/router/index.ts
- 与自进化相关的前端测试与快照
