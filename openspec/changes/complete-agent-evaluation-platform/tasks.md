## 1. 数据模型与后端基础

- [ ] 1.1 扩展 eval 数据模型以支持 score 状态、trial 快照、run 快照、claim-evidence、review 审计和导出元数据，并通过后端模型单元测试验证旧数据兼容
- [ ] 1.2 补齐数据集版本快照语义，创建 run 时固化 dataset version、case 内容、scorer 配置、judge 配置和数据窗口，并通过 runner service 测试验证可复现
- [ ] 1.3 增加 scorer registry 状态枚举，支持 `passed`、`failed`、`skipped`、`not_configured`、`error`，并通过 scorer hub 测试验证未启用 scorer 不进入待复核队列

## 2. 数据集与 Case 管理

- [ ] 2.1 在数据集详情页实现 Case 编辑和删除，并通过前端 type-check、组件交互测试或手动验收验证版本号更新
- [ ] 2.2 增加内置 Golden Set 后台导入接口和按钮，并通过 API 测试验证重复导入不产生重复 Case
- [ ] 2.3 增加 JSON/CSV/Excel 批量导入 Case 能力，并通过导入样例测试验证字段校验、错误提示和部分失败报告
- [ ] 2.4 增加 Case 批量标签、类别、难度和评分标准编辑，并通过页面操作验收验证批量修改结果
- [ ] 2.5 增加数据集版本发布 UI，并通过 API 和页面验收验证指定版本可用于后续 run
- [ ] 2.6 增加空数据引导，展示添加 Case、导入 Golden Set、批量导入和 Bad Case 回流入口，并通过页面空状态验收验证

## 3. 运行详情、报告与指标

- [ ] 3.1 在运行详情页增加 run 指标摘要，展示成功率、失败率、`pass@k`、`pass^k`、评分聚合、延迟和成本，并通过 `/api/eval/runs/{run_id}/metrics` 验证数据一致
- [ ] 3.2 增加 trial 详情视图，展示输入、Final Output、错误、token、成本、评分、复核状态和 trace 入口，并通过已完成 run 手动验收验证无需翻 trace 即可看到最终输出
- [ ] 3.3 增加运行报告页，展示 run 配置、dataset version、聚合指标、评分汇总、失败聚类、成本、延迟和复核结果，并通过 `/api/eval/report/{run_id}` 验证字段覆盖
- [ ] 3.4 增加报告导出能力，支持 JSON 和 CSV 导出，并通过导出文件内容验收验证
- [ ] 3.5 增加 run 对比页面，支持多 run 并排比较指标、scorer、成本、延迟和失败聚类，并通过两个历史 run 手动验收验证

## 4. 评分、Judge 与人工复核

- [ ] 4.1 在新建运行页增加评分器选择、judge model、rubric version、低置信阈值和复核策略配置，并通过 API payload 验证配置被保存到 run
- [ ] 4.2 在人工复核页补齐 Case 输入、Agent 输出、trace 证据、历史评分、judge 原始输出和维度理由，并通过低分样本手动验收验证
- [ ] 4.3 增加复核后动作，支持标记通过/失败、调整分数、加入 Bad Case、回流到指定数据集，并通过 API 测试验证审计字段写入
- [ ] 4.4 增加复核队列筛选，支持 run、dataset、score source、风险等级、置信度、是否已复核，并通过页面筛选验收验证

## 5. Claim-Evidence 与 Trace 下钻

- [ ] 5.1 实现 claim 抽取结构，支持从 Final Output 提取可验证 claim，并通过 scorer 单元测试验证输出 schema
- [ ] 5.2 实现 claim -> evidence 映射，记录证据片段、来源、trace event id、verdict、confidence 和 reason，并通过 grounding scorer 测试验证 `supported`、`weakly_supported`、`unsupported`、`contradicted`
- [ ] 5.3 在复核页和报告页展示 claim-evidence 对照，并通过人工验收验证可从 claim 跳转到对应 trace 片段
- [ ] 5.4 增强 trace 回放，按 LLM、tool、skill、swarm、evidence 分组展示，并通过真实 trial trace 验收验证

## 6. 趋势、治理与观测

- [ ] 6.1 增强质量趋势页，增加图例、口径说明、阈值线、`pass@k`/`pass^k` 切换和趋势点下钻，并通过历史 run 数据验收验证
- [ ] 6.2 增强失败聚类，按错误类型、工具、数据源、评分维度聚类，并通过失败 trial 样本测试验证聚类结果
- [ ] 6.3 完成 Release Gate 配置页面和检查结果页面，并通过低于阈值的 run 验证阻断原因
- [ ] 6.4 增加定时回归任务配置和运行记录，并通过禁用默认状态和手动触发验收验证
- [ ] 6.5 增加线上抽样入口和 Bad Case 回流闭环，并通过线上样本 API 测试验证样本入池
- [ ] 6.6 增加成本预算、告警订阅和第三方观测配置页面，并通过配置保存和告警检查 API 测试验证

## 7. 验证与文档

- [ ] 7.1 补充后端 API、service、scorer 和 migration 相关测试，并验证评测相关测试通过
- [ ] 7.2 补充前端 type-check、关键页面单元测试或交互验收脚本，并验证 `npm run type-check` 通过
- [ ] 7.3 更新评测平台使用文档和生产运维说明，并通过文档检查确认覆盖数据集、run、report、review、grounding、gate 和告警流程
