## Context

现有 `add-agent-evaluation-platform` 已实现评测集、Case、run、trial、trace、scorer、人工复核、bad case、趋势、报告和 gate 的基础 API/页面，但 UI 和数据结构仍偏 MVP。当前最大问题是评测结果不可直接审计：最终输出埋在 trace 里，judge 结论缺 evidence 对照，趋势和报告缺下钻，Case/数据集缺生产维护入口。

## Goals / Non-Goals

**Goals:**
- 把评测后台补成管理员可独立闭环使用的生产工作台。
- 让每个 trial 能从指标一路下钻到输入、最终输出、评分、证据、trace 和复核结果。
- 让评分器配置、judge 配置、数据集版本和 run 结果都可复现、可审计。
- 支持 claim -> evidence 的细粒度 grounding 结果。
- 支持 run 报告、趋势对比、release gate、告警和导出。

**Non-Goals:**
- 不在本 change 实现自进化候选生成和自动写回流程。
- 不改变普通用户投资分析主流程。
- 不引入必须联网的新评分框架作为硬依赖；第三方 scorer 仍应可选启用。

## Decisions

### 1. 以 run/trial 为分析中心

运行详情是管理员最常用入口，应从 run 摘要进入 trial 详情，再进入 trace、score、review、bad case。  
替代方案是把所有内容放在趋势页或报告页，但那会让定位单个问题变慢。

### 2. Final Output 独立展示

trial 详情必须直接展示 `output_data`，并保留 JSON/Markdown 展示能力。  
Trace 继续承担过程回放，不再承担最终输出展示职责。

### 3. Score 状态显式化

评分结果需要区分 `passed`、`failed`、`skipped`、`not_configured`、`error`。  
这样 DeepEval/Ragas/Promptfoo 未安装时不会被误当成真实低分。

### 4. Claim-evidence 作为结构化评分结果

Grounding scorer 输出应包含 claim 列表、证据引用、证据片段、来源、trace event id、verdict 和 reason。  
LLM judge 仍保留整体质量裁决，但不能代替 grounding。

### 5. 数据集版本使用快照语义

创建 run 时需要锁定 dataset version、case 内容、scorer 配置、judge 配置和数据窗口。  
否则金融行情、新闻、财报等时变数据会导致复盘不可靠。

### 6. UI 下钻优先于堆看板

趋势页和报告页只承担发现问题和汇总展示；具体判断必须能跳到 run、trial、case、score、bad case。  
这比单纯增加图表更符合评测工作流。

## Risks / Trade-offs

- [Risk] claim 抽取和证据匹配本身可能误判 -> Mitigation: 标注置信度，保留原文片段和人工复核入口。
- [Risk] 页面信息量过大 -> Mitigation: 使用摘要卡片、详情抽屉、tabs 和可折叠 JSON，默认展示关键路径。
- [Risk] 数据快照增加存储成本 -> Mitigation: 保存引用和必要摘要，原始大对象按配置保留。
- [Risk] 第三方 scorer 依赖复杂 -> Mitigation: 统一 scorer registry 和状态枚举，缺依赖时跳过而不是失败。

## Migration Plan

1. 对现有 eval collections 增量补字段，保持旧数据可读。
2. 先补 API 返回兼容字段，再补前端展示。
3. 对旧评分结果缺少 claim/evidence 的情况显示为未生成，不影响历史 run 查看。
4. Release gate、定时任务、观测配置默认关闭，由管理员显式启用。
