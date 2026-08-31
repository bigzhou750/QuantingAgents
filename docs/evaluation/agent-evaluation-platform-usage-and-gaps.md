# Agent Evaluation Platform Usage and Gaps

## Trial 数是什么

Trial 是同一个评测 Case 的一次独立运行。

如果一个 Case 的输入是：

```json
{
  "prompt": "请分析贵州茅台的基本面、估值和主要风险。"
}
```

那么：

- Trial 数 = 1：这个 Case 只跑 1 次。
- Trial 数 = 3：这个 Case 会用同样输入连续跑 3 次，生成 3 条独立 trial 结果。

Agent 输出具有不稳定性。同一个 prompt 可能因为模型采样、工具返回、网络、数据源、Agent 路径选择不同而产生不同结果。Trial 数用于评估稳定性，而不是扩大评测集规模。

常见用法：

- 日常冒烟测试：Trial 数设为 1，快速判断主流程是否可用。
- 版本回归测试：Trial 数设为 3，观察同一 Case 是否稳定通过。
- 关键发布前测试：Trial 数设为 5 或更多，用于计算 pass@k、pass^k、失败率、方差和成本。

示例：

一个数据集有 20 个 Case，Trial 数设为 3，则本次运行会产生：

```text
20 cases * 3 trials = 60 trials
```

## 当前后台使用流程

1. 打开 `Agent 评测 -> 评测集管理`。
2. 点击 `创建评测集`，创建一个空评测集。
3. 进入数据集详情页。
4. 点击 `添加用例`。
5. 填写 Case 的输入、期望输出和评分标准。
6. 添加足够 Case 后，点击 `运行评测`。
7. 在 `新建评测运行` 页面选择数据集版本、Trial 数和超时时间。
8. 创建并启动评测运行。
9. 在运行详情页查看 trial 状态、输出、trace、评分和失败原因。
10. 对失败样本进行人工复核或回流到 Bad Case 池。

## 质量趋势页面怎么看

当前 `质量趋势` 页不是完整 BI 看板，而是一个轻量的运行健康概览，主要看四类信息：

- `成功率趋势`：每次运行的总体通过率，越高越好。
- `评分维度趋势`：最近若干次运行里，各评分维度的分数变化。
- `最新成功率`：最近一次运行的总体成功率。
- `平均延迟(ms)` 和 `总成本(USD)`：最近一次运行的性能和成本开销。
- `失败模式数`：当前能归到多少类失败模式。

读法建议：

1. 先看成功率有没有连续下滑。
2. 再看延迟和成本有没有同步上升。
3. 再看失败聚类是否集中在同一种错误模式。
4. 最后结合具体 run 详情确认是数据集变化、模型变化还是工具链路退化。

当前这个页面难懂，主要因为：

- 图表是简化版条形趋势，没有坐标轴、阈值线和图例。
- `评分维度趋势` 直接把多个分数压在一行标签里，缺少分组和排序。
- 没有把趋势和具体 run、trial、case 的跳转关系串起来。
- 没有标明这些分数的口径、来源和是否已经经过 judge。

所以它更适合管理员快速扫一眼，不适合拿来做正式分析结论。

## pass@k / pass^k 应该在哪看

这两个指标不适合放在日常首页总览里，更适合放在以下位置：

- 运行详情页的“指标摘要”：看单次 run 的稳定性。
- 运行报告页：用于对外汇报、复盘和留档。
- 版本对比页：比较新模型、新 prompt、新工具链是否提升稳定性。
- Release Gate：作为发版门槛，尤其是 `pass@3`、`pass@5`。

推荐理解方式：

- `pass@k`：同一个 Case 连跑 k 次，至少成功一次的概率，更偏“覆盖率”。
- `pass^k`：同一个 Case 连跑 k 次，全部成功的概率，更偏“稳定性”。

使用约束：

- 当 `num_trials = 1` 时，这两个指标信息量很低，不应作为主视觉。
- 当 `num_trials >= 3` 时，它们开始对“偶发成功、重复不稳”很敏感，适合拿来做回归和门禁。
- 如果数据集里存在没启用评分器的样本，趋势和汇总页要区分 `skipped` 和真实低分，避免误判。

## Case 的基本结构

最小可用 Case：

```json
{
  "name": "A股基本面研究",
  "description": "验证 Agent 是否能输出基本面、估值和风险分析。",
  "category": "financial_research",
  "difficulty": "medium",
  "tags": ["golden", "stock", "evidence"],
  "input": {
    "prompt": "请分析贵州茅台的基本面、估值和主要风险。"
  },
  "expected_output": {
    "must_include": ["基本面", "估值", "风险"]
  },
  "scoring_criteria": {
    "min_output_length": 300
  }
}
```

字段说明：

- `input.prompt`：实际送给 Vibe Agent runtime 的问题。
- `expected_output.must_include`：答案中必须覆盖的关键点。
- `scoring_criteria.min_output_length`：最小输出长度。
- `tags`：用于筛选和组织 Case。
- `category`：用于聚合指标，例如金融研究、安全、工具过程、证据质量。
- `difficulty`：用于区分 easy、medium、hard 样本。

## 数据集从哪里来

### 1. 后台手工创建

适合少量人工维护的核心用例，例如：

- 高频金融研究问题
- 安全边界问题
- 工具调用问题
- 已知线上 bad case
- 回归必须覆盖的问题

### 2. 导入内置 Golden Cases

项目内置了首批 golden cases：

```text
app/services/eval/data/golden_cases.json
```

可通过脚本导入：

```bash
.venv/bin/python -m app.scripts.import_golden_cases
```

导入完成后，刷新 `评测集管理` 页面即可看到 `Vibe Agent Golden Set V1`。

### 3. Bad Case 回流

线上失败、人工复核失败、安全拦截和用户反馈可以进入 Bad Case 池，再回流成正式评测 Case。

当前已有后端接口和 Bad Case 页面，但从线上真实业务自动沉淀样本的流程还需要继续完善。

### 4. 后续批量导入

生产环境通常还需要从 JSON、CSV、Excel 或标注平台批量导入 Case。当前后台暂未提供批量导入 UI。

## 当前已具备能力

- 评测平台开关控制。
- 管理员访问控制。
- 评测集创建和列表。
- Case 新增和查看。
- 评测运行创建、启动、取消。
- 多 Trial 运行。
- Trial 超时、失败原因保存。
- Vibe Agent runtime 对接。
- Trace 标准化保存。
- 规则评分、金融质量评分、证据评分、轨迹评分、安全评分、LLM-as-judge 评分器基础能力。
- 人工复核 API。
- Bad Case 池和回流 API。
- 趋势、报告、告警、Release Gate 预留接口。
- Langfuse/Phoenix 观测适配预留。
- DeepEval/Ragas/Promptfoo 适配预留。

## 当前缺口

### P0：影响基本后台可用性

- Case 编辑入口：后端已有 `PUT /api/eval/cases/{case_id}`，前端详情页还没有编辑按钮。
- Case 删除入口：后端已有 `DELETE /api/eval/cases/{case_id}`，前端详情页还没有删除按钮。
- 默认 Golden Set 导入入口：目前需要运行脚本，后台没有“一键导入内置 Golden Cases”。
- 空数据引导：数据集为空时，页面应该提示添加 Case、导入 Golden Set 或从 Bad Case 回流。
- Trial 最终输出缺少独立入口：现在只能在 trace 里翻 `streaming` / `lifecycle` 事件，不方便直接对照评测结果查看 agent 最后说了什么。
- 运行详情上下文不足：当前主要能看 trial 列表和 trace 抽屉，但缺少同屏展示输入、最终输出、错误原因、token/成本、各维度评分和人工复核状态。
- 人工复核上下文仍不完整：已补上 judge 的原始输出、维度理由和证据引用，但复核人仍无法在同一视图里直接看到完整 Case 输入、Agent 输出、trace 证据和历史评分，难以彻底闭环。
- 指标摘要缺口：运行详情页和运行报告页没有把 `pass@k`、`pass^k`、分数聚合、延迟分布、成本分布放在同一个可扫描区域里，管理员需要来回跳接口或凭经验判断。

### P1：影响生产效率

- 批量导入 Case UI：支持 JSON、CSV、Excel 导入。
- Case 批量编辑：批量改标签、类别、难度、评分标准。
- 数据集版本发布 UI：后端有发布版本能力，前端入口还不完整。
- 评分器选择 UI：新建运行时应能选择规则评分、金融评分、证据评分、安全评分、LLM judge 等评分器。
- Judge 配置 UI：配置 judge model、rubric 版本、低置信阈值和复核策略。
- 运行详情分数展示：需要更完整展示每个 trial 的多维评分和评分原因。
- Trace 回放体验：当前偏基础，需要按 LLM、tool、skill、swarm、evidence 分层展示。
- 评分证据跳转：`trajectory`、`evidence_quality`、`llm_judge` 等评分原因应能跳转到对应 trace 片段、输出段落或证据引用。
- 人工复核完成后的闭环动作：复核后应支持一键标记为通过/失败、加入 Bad Case 池、回流到指定数据集，并保留复核原因。
- 未启用评分器的噪音控制：DeepEval、Ragas、Promptfoo 等依赖未安装或未启用时，应显示为 `not_configured`/`skipped`，不应作为低分项进入待复核队列。
- 复核队列筛选：人工复核页需要按 run、dataset、score source、风险等级、置信度、是否已复核筛选，避免所有低分混在一起。
- 运行报告页 UI：后端已有 `/api/eval/report/{run_id}`，但前端没有固定入口承载成一页可分享、可留档的报告。
- 指标钻取：从 `pass@k`、趋势图、失败聚类点击后，应能直接下钻到对应 run / trial / case，而不是只停留在汇总层。
- Grounding / evidence scorer 需要升级成逐条 claim 对证据：现在的 `evidence_quality` 更像粗粒度启发式评分，还没有把“每个结论对应哪条证据、哪句原文、哪次检索”做成可审计链路。
- `llm_judge` 与 grounding 需要分工：judge 负责判断输出是否合理，grounding 负责验证每个 claim 是否有证据支撑，不能混成一个黑盒分数。

### P2：趋势页可解释性增强

- 加图例和口径说明：成功率、评分分数、延迟、成本分别代表什么。
- 加时间轴和阈值线：让用户一眼看出是在改善还是恶化。
- 评分维度拆分展示：不要把所有 score 标签挤在一行。
- 趋势联动跳转：点击某条趋势应直接跳到对应 run 或 trial。
- 区分可评分和不可评分样本：没有启用 judge 的样本不要混在同一张趋势图里。
- 趋势页加入 pass@k / pass^k 切换：对多 Trial 数据集，应可切换看 `pass@1`、`pass@3`、`pass^3` 这类稳定性指标。

### P2：证据链能力增强

- Claim 抽取：把最终输出拆成一条条可判定的事实或结论。
- Claim 对证据映射：每条 claim 需要回链到 trace、检索结果或外部文档引用。
- 证据可视化：复核页需要把 claim、证据片段、原文高亮、检索来源并排展示。
- 证据缺失分级：把“无证据”“证据弱”“证据冲突”“已证实错误”分开，而不是统一叫事实造假。

### P2：生产治理增强

- CI/Release Gate 接入：把评测运行接入发布流程。
- 定时回归任务：每天或每次模型配置变更后自动跑关键集。
- 线上抽样闭环：从真实 Agent 会话抽样进入评测或 Bad Case。
- 失败聚类增强：按错误类型、工具、数据源、评分维度聚类。
- 数据快照和可复现：金融行情、新闻、财报数据需要保存时间窗口和数据快照引用。
- 成本预算面板：按 run、dataset、scorer、judge 统计 token 和成本。
- 第三方观测接入配置页：Langfuse、Phoenix 等目前是配置项，不是后台可视化配置。

## 进一步优化建议

如果要继续把它做成真正可长期使用的生产工具，建议再补这些能力：

- Final Output 独立视图：trial 详情里单独展示 agent 最后输出，不要让人去 trace 里翻。
- Claim -> Evidence 对照：把最终输出拆成 claim，再逐条对证据和 trace 片段。
- Run 对比：两个或多个运行并排比较，方便看模型、prompt、工具链改动前后的差异。
- 可复现快照：把 dataset 版本、case 内容、scorer 配置、judge 配置、数据时间窗口固定下来。
- 结果钻取链路：趋势页、报告页、失败聚类、Bad Case、trial、case 之间互相可跳转。
- 批量导入 / 导出：支持 JSON、CSV、Excel 导入，结果也要能导出给研发和审计。
- Case 去重和版本历史：新增重复提示、相似 case 发现、修改历史。
- 审计与协作：谁复核、谁改分、谁回流 bad case，要有完整历史记录。
- 告警和订阅：pass@k 回退、成本暴涨、失败率上升时自动通知。

## 自进化闭环

自进化不要做成“评测完自动改生产”，而要做成受控循环。一个完整闭环可以拆成五段：

### Trigger

- 评测运行完成。
- 质量趋势下滑。
- 某类失败模式持续出现。
- Bad Case 数量超过阈值。
- 定时回归任务触发。

### Proposal

- 生成候选变更草案。
- 变更对象只限于 Skill、Prompt、routing policy、grounding policy、rubric、case。
- 每个候选都要带 diff、原因、影响面和回滚方式。

### Verify

- 在固定 dataset version 上回放。
- 跑 `pass@k`、`pass^k`、grounding、judge、延迟、成本。
- 通过 trace 和 claim-evidence 对照检查问题是否真的被修正。

### Promote

- 通过人工审批或门禁后，才写回正式版本。
- 版本号、修改说明、验证结果必须一并保存。

### Rollback

- 验证不通过或线上回退时，直接切回上一个稳定版本。
- 保留失败候选，作为下一轮分析样本。

### 状态与控制

- 所有候选变更要版本化保存，不能直接覆盖。
- 只允许改受控 artifact，不允许 agent 自由改核心代码。
- 自动化程度应可配置为 `manual`、`semi-auto`、`auto`。
- 生产环境必须有 budget、审批和 stop hook。

### 和当前平台的对应关系

- `eval run` 是 verify 引擎。
- `bad case` 是问题样本池。
- `review` 是人工 gate。
- `report / trends / release gate` 是判断是否 promote 的依据。
- `skill`、`rubric`、`policy` 是真正被更新的资产。

## 建议下一步

优先补 P0：

1. 在数据集详情页补 Case 编辑和删除。
2. 增加“一键导入 Golden Set”接口和按钮。
3. 给空数据页面加明确引导。
4. 在运行详情页补完整 trial 上下文：输入、输出、trace、错误、token/成本、评分和复核状态。
5. 在人工复核页补上下文抽屉，并支持复核后回流 Bad Case。
6. 将未安装/未启用的第三方评分器从待复核失败项中剔除，改为 skipped 状态。

完成 P0 后，这个平台才算是能由管理员在后台闭环使用，而不是研发半脚本半页面操作。

---

## 生产工作台升级说明（二期完成）

以下功能已在二期迭代中全部实现，覆盖数据集管理、运行详情/报告、评分/复核、Claim-Evidence grounding、趋势治理和测试验证。

### 数据集与 Case 管理

- **Case 编辑/删除**：数据集详情页支持单条 Case 编辑和删除（带确认弹窗）。
- **批量导入**：支持 JSON 数组批量导入 Case，逐条报告成功/失败。
- **Golden Set 导入**：一键从内置 golden set 导入标准评测用例（按名称去重）。
- **批量编辑**：多选 Case 后批量修改标签、分类、难度和评分标准。
- **版本发布**：数据集支持版本号管理和发布。
- **空状态引导**：空数据集页面展示四种操作入口按钮。

### 运行详情与报告

- **指标摘要**：成功率、失败率、pass@k、pass^k、平均延迟、总成本。
- **Trial 详情抽屉**：Final Output 突出展示，输入数据、错误信息、Token 用量、评分表格。
- **自动刷新**：运行中/等待中时 5 秒轮询更新进度。
- **评测报告页**：独立报告视图，支持 JSON/CSV 导出（CSV 含 BOM 兼容 Excel）。
- **运行对比**：选择 2-4 个运行进行指标并列对比。
- **Run Snapshot**：创建运行时锁定 case 内容、scorer 配置、judge 配置和数据窗口，确保可复现。

### 评分、Judge 与人工复核

- **ScoreStatus 枚举**：passed / failed / skipped / not_configured / error，避免未启用评分器污染复核队列。
- **Scorer 可用性检查**：外部库适配器（deepeval/ragas）未安装时显示 not_configured 而非报错。
- **人工复核增强**：75% 宽度对话框，左右对照 Case 输入和 Agent 输出，Judge 维度理由表格，历史评分参考。
- **复核动作**：approve / reject / adjust_score / add_bad_case / reflow（回流到指定数据集）。
- **复核审计轨迹**：每次复核操作记录 reviewer、action、old/new score、comment、timestamp。
- **筛选条件**：按 Run ID、评分来源、置信度阈值过滤待复核列表。

### Claim-Evidence Grounding

- **Claim 抽取**：evidence_scorer v2.0 从 Final Output 按句子分割提取可验证 claim。
- **Evidence 映射**：使用 n-gram 重叠算法将 claim 匹配到 trace 中的 evidence/retrieval/citation 事件。
- **Verdict 判定**：supported / weakly_supported / unsupported / contradicted，附置信度和理由。
- **前端展示**：人工复核对话框中显示 Claim-Evidence 表格；报告页显示 verdict 分布汇总和覆盖率进度条。
- **Trace 分组增强**：按 LLM/Tool/Skill/Swarm/Evidence 类型分组展示，带图标标签。

### 趋势、治理与观测

- **质量趋势增强**：双柱图（成功率 + pass@k/pass^k 切换），阈值参考线（发布门禁/告警），口径说明面板，趋势点下钻到运行详情。
- **多维失败聚类**：除错误消息外，增加按评分维度和数据来源的失败分布统计。
- **Release Gate 配置**：可视化配置页面，支持启用/禁用、设置成功率/pass@3/失败率阈值、必须通过的评分器列表。
- **告警检查**：一键检查当前告警状态，展示触发的告警规则和当前值。
- **回归任务**：CRUD API 支持定时回归配置（默认禁用），手动触发运行并记录 last_run_id。
- **线上抽样入池**：Bad Case 池新增"线上抽样入池"入口，支持填写 input/output/failure_reason/session_id。
- **Trial 转 Bad Case**：API 端点支持将失败 trial 直接转换为 Bad Case。

### 测试与验证

- **后端测试**：83 个评测相关测试全部通过，覆盖数据模型、scorer、metrics、路由。
- **前端类型检查**：`vue-tsc --noEmit` 零错误通过。
- **向后兼容**：所有新增字段有默认值，旧数据无需迁移即可正常读取。
