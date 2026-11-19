## 1. 一期：Eval 基础设施 MVP

- [x] 1.1 在 `app/` 新增 Agent 测评模块结构和配置开关，验证默认关闭时不暴露评测后台 API 和页面入口
- [x] 1.2 设计并实现数据模型（版本化已实现：_bump_patch_version 自动递增，list_cases 支持 version 过滤，publish_version 手动发版；注：update_case 就地覆盖不保留历史快照，如需回放旧版本需后续扩展）
- [x] 1.3 实现评测集和 case 的后台 API + 权限校验（verify_eval_access 链式依赖 get_current_user 并校验 is_admin）
- [x] 1.4 实现 Eval Runner 基础服务，对接 Vibe Agent runtime
- [x] 1.5 为 Eval Runner 增加多 trial、超时、取消、失败保存和预算限制
- [x] 1.6 实现 Agent Trace Adapter（VIBE_EVENT_TYPE_MAPPING 覆盖 50+ 事件类型，未知事件归为 LIFECYCLE 而非 ERROR）
- [x] 1.7 实现基础 ScorerHub 和确定性评分器
- [x] 1.8 新增后台页面：评测集列表、运行列表、运行详情、数据集详情、Bad Case 池（路由已注册，侧边栏入口已添加）
- [x] 1.9 准备首批 golden cases + vendor import 修复（PersistentMemory 导入已 try/except 降级）
- [x] 1.10 增加后端和前端基础测试（17 tests passed）

## 2. 二期：质量评分、LLM Judge 与人工复核

- [x] 2.1 实现 LLM-as-judge 评分器（llm_judge_scorer.py，DashScope 集成 + mock 降级）
- [x] 2.2 实现金融质量评分 rubric（DEFAULT_FINANCIAL_RUBRIC 5 维度加权）
- [x] 2.3 实现证据质量评分（evidence_scorer.py，4 维度启发式分析）
- [x] 2.4 实现工具与轨迹评分（trajectory_scorer.py，冗余检测 + 效率指标）
- [x] 2.5 接入 DeepEval 适配器（deepeval_adapter.py，未安装时优雅降级）
- [x] 2.6 接入 Ragas 适配器（ragas_adapter.py，未安装时优雅降级）
- [x] 2.7 实现人工复核 API 和数据模型（POST /scores/human-review, GET /scores/pending-review）
- [x] 2.8 实现 pass@k/pass^k 和聚合指标（metrics_service.py + POST /metrics/compare）
- [x] 2.9 实现 bad case 池和失败回流（bad_case_service.py + full CRUD API）
- [x] 2.10 增加评分器和人工复核测试（22 tests passed）

## 3. 三期：生产观测、安全红队与线上闭环

- [x] 3.1 实现 Langfuse/Phoenix 观测适配（observability_adapter.py，配置开关控制启停）
- [x] 3.2 Trace 脱敏与大文本外存（redact_sensitive_data + truncate_large_text + sanitize_trace_data）
- [x] 3.3 安全红队适配器（redteam_adapter.py，8 条内置用例，Promptfoo 可选）
- [x] 3.4 SafetyScorer（safety_scorer.py，5 项安全检查 + 风险标签）
- [x] 3.5 线上 eval 抽样 + Bad Case 回流入口（POST /online-sample）
- [x] 3.6 质量趋势与失败聚类页面（GET /trends + Trends.vue）
- [x] 3.7 告警与报告导出（GET /alerts/check + GET /report/{run_id}）
- [x] 3.8 Release gate 预留配置（ReleaseGateConfig + GET/PUT/POST API，默认关闭）
- [x] 3.9 端到端生产验收测试（30 tests passed，总计 69 tests 全部通过）
