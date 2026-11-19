## Why

当前自进化闭环已经具备提案、验证、审批、发布和回滚的基础模块，但关键安全边界仍停留在配置或约定层，候选 sandbox 未必真正进入评测 runner，审批和发布也可能绕过验证结果。需要把这些控制从“可调用能力”收紧为可审计、可阻断、可回滚的生产流程。

## What Changes

- 让 candidate artifact override 真正进入隔离的评测 runner，验证期间只读取候选版本，验证后清理 sandbox。
- 强化 proposal 状态机，禁止未验证提案直接审批或发布；promote 前必须检查验证结果、Release Gate、基线版本和人工审批。
- 让 allowlist、change budget、每日验证预算、重复失败、风险退化和 stop hook 成为强制策略。
- 接入自进化定时触发器，默认关闭，启用后使用配置的 cron 执行并记录运行结果。
- 增加 proposal/artifact 的乐观锁和幂等控制，防止并发 promote、rollback 或版本覆盖。
- 完善 Skill、Prompt、Policy、Rubric、Case 的正式版本与候选版本读取边界，禁止线上运行读取未批准资产。
- 完善 promote/rollback 的一致性、runtime 缓存失效和发布后 smoke test。
- 对相同失败模式进行 proposal 去重、冷却和数量限制，避免自进化循环无限增长。
- 将线上 trace、用户反馈、Bad Case、发布版本和后续质量指标串成可追踪闭环，并完善通知与审计记录。

## Capabilities

### New Capabilities

- `agent-self-evolution-production-governance`: 覆盖候选 sandbox 执行、严格状态机、验证门禁、预算与 stop hook、版本锁、发布回滚一致性、线上反馈和通知审计。

### Modified Capabilities

本项目当前自进化能力尚未同步为主规范，因此本次以生产治理新能力承接现有自进化模块的加固要求。

## Impact

- Backend：影响 `app/services/evolution/*`、`app/services/eval/runner_service.py`、`app/routers/evolution.py`、评测 runner 配置和调度器。
- Frontend：影响自进化提案、验证、Artifact、回执和配置页面，增加门禁失败、预算、版本冲突和 stop 状态展示。
- API：现有自进化 API 保持路径兼容，增强状态校验、错误码、审计字段和幂等语义。
- Configuration：新增或扩展 sandbox、预算、冷却、cron、allowlist、Release Gate、smoke test 和通知配置。
- Data：MongoDB 增加候选执行上下文、锁、stop 记录、发布后检查、线上反馈关联和通知发送记录。
- Runtime：候选验证使用隔离 artifact overlay；正式运行只能读取已批准的 active artifact。
- Security：禁止自动修改核心代码、评分口径、测试集和样本切分；生产 promote 默认必须人工审批。
- Compatibility：不改变现有研究、选股、模拟交易和评测业务链路；旧 proposal、verification、receipt 数据需要兼容读取。
