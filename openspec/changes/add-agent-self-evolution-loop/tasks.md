## 1. 数据模型与配置

- [ ] 1.1 新增自进化 proposal、artifact version、verification run、approval、receipt 数据模型，并通过模型单元测试验证序列化和旧数据兼容
- [ ] 1.2 新增自进化全局配置，支持 automation mode、trigger thresholds、allowlist、budget、human gate 和 stop hook，并通过配置测试验证默认生产安全
- [ ] 1.3 新增 artifact registry，登记 Skill、Prompt、Policy、Rubric、Case 的路径、类型、owner、当前版本和回滚策略，并通过 registry 测试验证禁止未登记资产

## 2. Trigger

- [ ] 2.1 接入 eval run completed 触发器，并通过模拟完成 run 验证能创建候选任务或建议
- [ ] 2.2 接入质量趋势回退触发器，并通过低于阈值的历史 run 数据验证触发条件
- [ ] 2.3 接入 Bad Case 阈值和失败聚类触发器，并通过重复失败样本测试验证聚类输入
- [ ] 2.4 接入定时任务触发器，默认关闭，并通过手动触发验收验证

## 3. Proposal

- [ ] 3.1 实现失败归因到变更面的映射，覆盖 grounding、tool 调用、输出格式、规划、安全、rubric 和 case 问题，并通过归因测试验证目标 artifact 类型
- [ ] 3.2 实现候选变更生成接口，输出 target artifact、diff、原因、关联样本、影响面、预算、风险和回滚方式，并通过 API 测试验证 schema
- [ ] 3.3 实现 forbidden target 拦截，禁止修改核心代码、测试集、评分口径和样本切分，并通过安全测试验证拒绝原因
- [ ] 3.4 在前端展示候选列表和详情，包含触发来源、失败模式、关联样本、diff 和状态，并通过页面验收验证

## 4. Verify

- [ ] 4.1 实现候选版本 sandbox/临时覆盖机制，使候选 Skill、Prompt、Policy、Rubric 或 Case 可用于验证 run，验证完成后不污染正式版本
- [ ] 4.2 复用 eval runner 创建候选验证 run，并通过 API 测试验证 baseline 与 candidate 均可追踪
- [ ] 4.3 输出验证对比结果，包含 `pass@k`、`pass^k`、grounding、judge、失败率、延迟、成本和新增 regression，并通过 service 测试验证
- [ ] 4.4 强制样本隔离，阻止候选流程访问测试集或改变 split，并通过隔离测试验证
- [ ] 4.5 在前端展示验证 run、指标对比和门禁结果，并通过页面验收验证

## 5. Promote 与 Rollback

- [ ] 5.1 实现审批接口，支持批准、拒绝、备注和审批人记录，并通过 API 测试验证审计字段
- [ ] 5.2 实现 promote 流程，只有验证通过且审批通过后写回正式 artifact 版本，并通过集成测试验证版本号和 receipt
- [ ] 5.3 实现 rollback 流程，支持回滚到指定稳定版本，并通过集成测试验证正式 artifact 恢复
- [ ] 5.4 实现 stop hook，在预算超限、重复失败、安全退化或门禁失败时停止闭环，并通过策略测试验证
- [ ] 5.5 在前端提供 approve、reject、verify、promote、rollback 操作，并通过手动验收验证状态流转

## 6. 审计、权限与通知

- [ ] 6.1 增加自进化权限控制，默认仅管理员可访问和操作，并通过权限测试验证普通用户被拒绝
- [ ] 6.2 增加 receipt 页面或详情区，展示触发原因、候选 diff、验证 run、审批、promote/rollback 和最终状态，并通过页面验收验证
- [ ] 6.3 增加自进化事件日志和可筛选审计列表，并通过 API 测试验证按状态、artifact、触发源查询
- [ ] 6.4 增加通知入口，支持 proposal 创建、验证失败、gate 失败、promote 成功和 rollback 完成，并通过配置保存测试验证

## 7. 验证与文档

- [ ] 7.1 补充后端模型、触发器、proposal、verify、promote、rollback、安全边界和权限测试，并验证自进化相关测试通过
- [ ] 7.2 补充前端 type-check、工作台页面和候选详情交互验收，并验证 `npm run type-check` 通过
- [ ] 7.3 更新自进化使用文档，覆盖 trigger、proposal、verify、promote、rollback、artifact registry、样本隔离和人工审批流程
