# Claim 级幻觉检测指标

评测系统将最终答案拆分为 Claim，并将人工真值与 Evidence scorer 的预测分开保存。
只有同时具备 `truth_label` 和 `prediction_label` 的 Claim 才参与分类指标计算。

## 标签

- `supported`：结论正确且有可靠证据支撑
- `unsupported`：结论没有可靠证据
- `contradicted`：结论与可靠证据冲突
- `excluded`：样本无法稳定判断，不参与指标计算

Evidence scorer 的 `unsupported` 和 `contradicted` 默认预测为幻觉；
`weakly_supported` 默认排除，具体口径通过评测配置确定。

## 指标

以 `unsupported` 和 `contradicted` 为正类：

```text
Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
F1        = 2 * Precision * Recall / (Precision + Recall)
```

结果同时返回 TP、FP、FN、TN、参与样本数、排除样本数、数据集版本、标签版本和评分器版本。
缺少真值或正类样本时返回 `not_available` 或空指标，不用 0 分代替。

Ragas 的 Faithfulness、Answer Relevancy 是连续质量分数，与上述 Claim 分类指标独立展示，不能直接互换。
