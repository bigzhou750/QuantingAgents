## 1. 状态模型与治理策略

- [x] 1.1 扩展 `app/models/evolution.py` 的 proposal、verification、receipt 和事件模型，增加基线版本、候选版本、overlay context、gate 结果、stop reason、锁和 smoke test 字段，并通过旧数据反序列化测试
- [x] 1.2 在 `app/services/evolution/` 新增统一 governance policy 服务，集中执行状态转换、allowlist、change budget、每日预算、质量门禁和 stop policy，并通过策略单元测试覆盖默认生产安全
- [x] 1.3 增加 proposal 指纹、冷却窗口和幂等键模型及索引，验证相同失败模式、artifact 和 run 不会重复创建 proposal
- [x] 1.4 增加治理配置持久化和 API，支持 overlay、预算、冷却、Release Gate、smoke test 和通知配置，并通过配置读写测试验证敏感字段不进入日志

## 2. Candidate Overlay 与 Runner 隔离

- [x] 2.1 在 `app/services/evolution/verification_service.py` 实现 candidate overlay manifest，记录 proposal、artifact、基线版本、候选版本、dataset version 和唯一 overlay id，并通过 manifest schema 测试验证完整性
- [x] 2.2 修改 `app/services/eval/runner_service.py` 和 runtime loader，使 verification run 真实读取 overlay 中的候选 Skill、Prompt、Policy、Rubric 或 Case，正式 run 不读取 overlay，并通过 fake runtime 对照测试验证
- [x] 2.3 将 overlay context 和实际加载 artifact/version 写入 trial trace、run snapshot 和 verification record，并通过 trace 集成测试验证可回放
- [x] 2.4 实现 verification 完成、失败、取消、超时后的 sandbox 清理和 cleanup failure 状态，清理失败时阻止 promote，并通过异常清理测试验证
- [x] 2.5 强制 candidate 数据集、split 和测试集隔离，验证 overlay 只能读取允许的数据窗口和 dataset version

## 3. 严格状态机与版本锁

- [x] 3.1 在 proposal service 中实现合法状态转换表，拒绝跳过 verifying、verified 或 approved 的转换，并通过状态机单元测试覆盖所有非法路径
- [x] 3.2 修改 approval service，只有 verification 完成且 gate 通过的 proposal 才能批准，并通过未验证、验证失败和重复审批测试验证
- [x] 3.3 在 promote service 中增加 verification、Release Gate、safety、grounding、成本、延迟和人工审批前置检查，并通过失败门禁测试验证不会写正式版本
- [x] 3.4 在 promote 前增加 artifact registry 乐观锁，基线版本变化时拒绝发布并要求重新验证；通过并发版本冲突测试验证
- [x] 3.5 为 approval、promote、rollback 和 stop 增加 request id、幂等键和原子状态更新，重复请求不得创建重复版本或 receipt

## 4. Allowlist、预算与 Stop Hook

- [x] 4.1 在 artifact registry 和 proposal service 中强制校验 artifact 已登记、类型/路径/section 匹配 allowlist，并通过核心代码、测试集、评分口径和未登记资产测试验证
- [x] 4.2 实现 proposal change budget 校验，限制修改文件、section、字符数和候选运行数量，并通过预算边界测试验证超限被拒绝
- [x] 4.3 实现每日 verification 次数和成本预算累计，超过预算时停止新验证、写入 `budget_exceeded` receipt 并通过 API 测试验证
- [x] 4.4 实现重复失败、safety degradation、Release Gate failure 和新增 regression 的 stop hook，验证 proposal 状态、停止原因和后续动作正确
- [x] 4.5 确保未配置或不可用的评分器不伪装成低分，并将其从 promote gate 和待复核队列中排除；通过 scorer 集成测试验证

## 5. 定时 Trigger 与线上反馈

- [x] 5.1 在 `app/main.py` 将 `EVOLUTION_SCHEDULE_CRON` 接入 APScheduler，默认关闭，启用后调用统一 scheduled check，并通过调度器测试验证注册/暂停行为
- [x] 5.2 为 scheduled trigger 增加时间窗口锁、proposal 去重和失败重试记录，验证重复调度不会创建重复提案
- [x] 5.3 将线上 run、trace、用户反馈、Bad Case、proposal、verification 和 release receipt 建立关联字段及索引，并通过线上样本 API 测试验证链路可查询
- [x] 5.4 实现发布后质量观测和退化判断，覆盖成功率、安全、grounding、成本和延迟阈值，并通过模拟退化样本验证 stop/rollback 建议
- [x] 5.5 完善通知发送适配和失败重试状态，覆盖 proposal 创建、验证失败、gate 失败、promote、rollback 和 stop，并通过通知失败测试验证不误报成功

## 6. Promote、Rollback 与 Runtime 一致性

- [x] 6.1 修改 promote 流程以原子更新 active artifact、proposal、receipt 和 audit log，并通过集成测试验证中途失败可补偿
- [x] 6.2 为 Skill promote/rollback 增加正式文件写回、runtime cache 失效和内容 hash 校验，并通过文件系统与缓存测试验证一致性
- [x] 6.3 实现发布后 smoke test，smoke test 失败时阻止完成发布或自动触发 rollback 建议，并通过 fake runtime 测试验证
- [x] 6.4 为 rollback 增加目标版本存在性、内容完整性、幂等和审计校验，并通过重复 rollback 与非法版本测试验证
- [x] 6.5 明确正式运行只读取 active approved artifact，candidate verification 只读取 overlay artifact，并通过权限边界测试验证

## 7. 前端治理工作台

- [x] 7.1 在 `frontend/src/views/Evolution/` 展示 proposal 的基线/候选版本、overlay 状态、gate 结果、stop reason、锁冲突和 smoke test 状态，并通过组件测试验证
- [x] 7.2 在 proposal 详情页禁用不满足状态机条件的 approve/promote 操作，展示明确失败原因，并通过交互测试验证
- [x] 7.3 增加预算、allowlist、冷却、定时 trigger、通知和 smoke test 配置入口，默认显示生产安全值，并通过前端 type-check 验证
- [x] 7.4 增加 promote/rollback receipt 详情，展示版本 diff、验证指标、审批、gate、smoke test、通知和审计链路，并通过页面验收验证

## 8. 集成验证与文档

- [x] 8.1 增加 trigger → proposal → overlay verify → gate → approval → promote → smoke test → rollback 的 Mongo/fake-runtime 集成测试，并验证旧流程兼容
- [x] 8.2 增加线上退化 → stop hook → rollback 建议 → 通知的集成测试，并验证敏感 prompt/output 已脱敏
- [x] 8.3 运行自进化、评测 runner、前端工作台和现有研究流程相关测试，确认生产闭环不会改变原有分析链路
- [x] 8.4 在 `docs/evaluation/` 或 `docs/self-evolution-guide.md` 更新生产运行手册，覆盖 overlay、门禁、预算、定时任务、promote、rollback、smoke test、通知和故障恢复
- [x] 8.5 运行 `openspec validate harden-agent-self-evolution-production-loop --strict`，并记录默认关闭、启用配置和完整链路验收结果
