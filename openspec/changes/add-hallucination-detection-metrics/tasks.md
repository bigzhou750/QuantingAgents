## 1. Claim 标签与数据结构

- [x] 1.1 扩展 `app/models/eval.py` 的 Claim 和评分结果模型，增加真值标签、预测标签、幻觉类型、标注来源及版本字段；通过现有模型测试并验证旧数据可正常反序列化
- [x] 1.2 定义 Claim 真值与幻觉预测的枚举、映射口径及 `weakly_supported` 处理配置；通过单元测试覆盖 supported、unsupported、contradicted、weakly_supported 四类状态

## 2. 幻觉预测与指标聚合

- [x] 2.1 在 `EvidenceQualityScorer` 中输出结构化幻觉预测及判定原因，保留证据匹配阈值和 scorer 版本；通过现有 evidence scorer 测试验证预测结果不改变原有 evidence score
- [x] 2.2 在评测服务层实现 Claim 级混淆矩阵聚合，计算 TP、FP、FN、TN、Precision、Recall、F1 及无证据结论放行率；通过纯函数单元测试验证公式、四类样本和空分母场景
- [x] 2.3 支持按幻觉类型、数据集版本和标签版本聚合指标，并返回样本量、分子、分母和不可计算原因；通过聚合测试验证分组结果和版本隔离

## 3. API 与结果展示

- [x] 3.1 扩展评测结果 API 返回幻觉指标、混淆矩阵、口径和版本信息，缺少真值时返回 `not_available` 而不生成伪指标；通过 API 测试验证新旧响应兼容
- [x] 3.2 在现有评测结果或报告页面增加幻觉指标展示及 Claim 下钻入口，区分 evidence/Ragas 连续分数与分类指标；通过前端类型检查和关键页面交互测试

## 4. 数据与集成验证

- [x] 4.1 增加 Claim 标注导入或录入所需的数据校验，拒绝未知标签、缺少版本或无效 Claim 引用；通过正常、重复和非法输入测试
- [ ] 4.2 使用固定样本运行完整评测链路，验证人工真值、Evidence scorer 预测、指标聚合和 API 展示结果一致；通过 `pytest tests/` 中相关评测测试并核对混淆矩阵
- [x] 4.3 更新评测文档，说明标签定义、指标公式、样本分母、版本语义和 Ragas 指标边界；通过文档审查确认不将 evidence score 或 Ragas 分数误称为 Recall/F1
