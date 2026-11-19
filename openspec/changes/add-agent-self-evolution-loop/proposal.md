## Why

评测平台只能发现问题，不能自动把经验沉淀回 Skill、Prompt、Policy、Rubric 和 Case。需要新增受控自进化闭环，把失败样本、人工复核和评测指标转化为候选变更，并通过固定评测集验证后再进入正式版本。

## What Changes

- 新增自进化工作台：展示触发事件、失败模式、候选变更、diff、验证运行、审批状态、promote/rollback 记录。
- 新增 Trigger 机制：支持评测完成、趋势下滑、bad case 阈值、失败聚类和定时任务触发。
- 新增 Proposal 机制：根据失败归因生成 Skill、Prompt、routing policy、grounding policy、rubric、case 的候选修改。
- 新增 Verify 机制：候选版本必须在固定 dataset version 上回放，产出 pass@k、pass^k、grounding、judge、延迟、成本和回归风险。
- 新增 Promote/Rollback 机制：通过人工审批或 release gate 后才写回正式版本，不通过则保留候选并回滚。
- 新增版本化资产管理：保存候选 artifact、diff、原因、影响面、验证结果、审批记录和生效版本。
- 保持生产安全边界：agent 不得自由修改核心代码，不得访问测试集，不得改变评分口径和数据切分。

## Capabilities

### New Capabilities
- `agent-self-evolution-loop`: 覆盖 Agent 自进化的 trigger、proposal、verify、promote、rollback、版本化资产和工作台交互。

### Modified Capabilities
- 无。

## Impact

- Backend: 新增自进化服务、候选变更模型、触发器、审批 API、验证运行编排和 artifact 写回适配。
- Frontend: 新增自进化工作台页面，支持候选列表、diff 查看、验证结果、审批、promote、rollback 和审计记录。
- Runtime assets: 受控更新 `vibe_agent_runtime/vendor/src/skills/*/SKILL.md`、policy/rubric 配置、eval case 数据。
- Data: MongoDB 增加 self-evolution proposals、artifact versions、verification runs、approval records、receipts。
- Safety: 新增 allowlist、change budget、human gate、stop hook、rollback policy，防止自动化改坏生产。
