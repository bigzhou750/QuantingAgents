## 1. 数据模型与策略版本

- [ ] 1.1 在 `app/models/` 新增 `SkillRoutingIndex` 模型，保存 Skill 名称、描述、触发边界、负向规则、工具依赖、类别、版本、owner 和路由状态，并用旧数据缺字段 fixture 验证可读（spec: Skill routing index must be maintained; design: 3）
- [ ] 1.2 新增 `RoutingStrategy` 模型，保存阶段配置、TopK、embedding/rerank 模型、超时、降级模式和不可变版本，并用策略创建/回滚测试验证版本指针（spec: Router strategy and deployment must be versioned; design: 2, 7）
- [ ] 1.3 新增路由策略评测 Pending/Active 状态和索引快照，Mongo 建立 `skill_routing_index`、`routing_strategies` 索引，并用 CRUD 测试验证（spec: Skill routing index must be maintained; design: 3, 7）

## 2. SkillRouter 服务

- [ ] 2.1 新增 `app/services/skill_routing/` 下的 `SkillRouter` 服务，实现输入任务到候选 Skill 列表的接口，并用无候选、单候选、多候选测试验证返回结构（spec: Router must produce a bounded candidate subset; design: 1）
- [ ] 2.2 实现规则召回阶段，基于路由索引的触发边界、负向规则和工具依赖过滤，并用正/负/边界 case 验证召回正确（spec: Router must produce a bounded candidate subset; design: 2）
- [ ] 2.3 实现可配置 Embedding 召回和 LLM 重排阶段，策略未配置时跳过并记录 `stage_disabled`，用 mock 适配器测试验证 TopK 和置信度输出（spec: Router must produce a bounded candidate subset; design: 2）
- [ ] 2.4 为每个路由调用生成策略版本、候选来源、置信度、未选原因和耗时字段，用 trace 测试验证策略字段完整（spec: Route decisions must be auditable; design: 2）

## 3. Runtime Context 集成

- [ ] 3.1 修改 `vibe_agent_runtime/vendor/src/agent/context.py`，启用路由时只注入 `RoutingResult` 候选 Skill 摘要，并用单元测试验证摘要白名单（spec: Main agent context must consume routed candidates; design: 4）
- [ ] 3.2 修改 session/context 构建链路，路由禁用时保持现有全量摘要逻辑，并用旧行为 fixture 验证兼容（spec: Main agent context must consume routed candidates; design: 4）
- [ ] 3.3 扩展 `skill_route` 事件，记录策略版本、候选来源、未选原因、路由耗时和 fallback 标记，并兼容已有 `skill_route` 字段（spec: Route decisions must be auditable; design: 4）
- [ ] 3.4 记录“加载了不在候选集中的 Skill”，作为策略遗漏和静默绕过证据，并用 runtime trace 测试验证（spec: Route decisions must be auditable; design: 4）

## 4. 降级与风险控制

- [ ] 4.1 新增路由失败降级策略，低风险任务回退为全量摘要并标记 `routing_failed`，用降级测试验证返回结果和 trace 状态（spec: Router failure must degrade safely; design: 5）
- [ ] 4.2 高风险任务路由异常时暂停后续 Skill 加载并创建人工复核，用高风险 fixture 验证不会静默回退（spec: Router failure must degrade safely; design: 5）
- [ ] 4.3 路由输入、候选结果和原始 trace 在降级时全量保存，缺字段时标记 `reason_unavailable`，用审计测试验证（spec: Route decisions must be auditable; design: 5）

## 5. 路由指标与评测

- [ ] 5.1 新增路由指标模型和聚合服务，输出召回率、准确率、误触发率、漏触发率、静默绕过率、路由延迟和成本，并用空样本/缺失 Ground Truth 测试验证不伪造指标（spec: Routing metrics must be observable; design: 6）
- [ ] 5.2 复用 `add-skill-execution-evaluation-and-regression` 的 expected_route case 和 route scorer，接入策略版本对比，并用同一数据集的新旧策略 run 验证指标差异（spec: Router strategy and deployment must be versioned; design: 6）
- [ ] 5.3 将路由策略评测 run 接入现有 `agent-evaluation-platform` 的 run/trial/trend 链路，未启用显式路由时显示 `not_configured`，用兼容测试验证（spec: Evaluation platform must expose explicit routing strategy metrics; design: 6）

## 6. API 与前端

- [ ] 6.1 新增路由策略 CRUD、启用、灰度、回滚和评测 run API，权限仅管理员可写，用 API 权限测试验证（spec: Router strategy and deployment must be versioned; design: 7）
- [ ] 6.2 在评测后台新增路由配置页和路由指标页，展示候选命中、策略版本、误触发/漏触发和静默绕过，用 type-check 和组件测试验证（spec: Evaluation trial details must show explicit routing decisions; design: 6）
- [ ] 6.3 在 trial 详情中展示路由输入、候选 Skill、最终路由、策略版本、耗时和未选原因，旧 trial 显示 `legacy_unverified`，用前端测试验证（spec: Evaluation trial details must show explicit routing decisions; design: 4, 6）

## 7. 验证与文档

- [ ] 7.1 运行模型、router、context、trace、降级、指标和评测相关 pytest，并执行 `openspec validate add-explicit-skill-routing-layer --strict`（spec: 全部; design: Test Strategy）
- [ ] 7.2 运行 `npm run type-check` 和相关前端组件测试，验证路由禁用和旧 run 页面不报错（spec: Evaluation platform must expose explicit routing strategy metrics; design: Test Strategy）
- [ ] 7.3 更新文档，说明路由策略、索引派生、降级模式、指标口径和与 Skill 评测 change 的依赖关系，通过文档审查确认一致（spec: 全部; design: Migration Plan）
