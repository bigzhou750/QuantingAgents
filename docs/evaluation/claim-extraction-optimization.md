# Claim 抽取问题与优化方案

> 记录日期：2026-09-11
>
> 相关实现：`app/services/eval/scorers/evidence_scorer.py`
>
> 适用范围：评测端 Claim-Evidence grounding

## 1. 问题概述

当前 `EvidenceQualityScorer._extract_claims` 使用简单的正则规则从 Agent Final Output
中抽取 Claim：

1. 按 `。！？.!?\n` 分割文本；
2. 去除空白并保留长度大于等于 8 的片段；
3. 最多取前 20 个片段；
4. 每个片段直接构造为 `ClaimEvidence`。

这个实现把“文本片段”近似当成“事实 Claim”，没有充分识别 Markdown 结构、段落换行、
列表、表格以及被 PDF/OCR 或模型输出拆开的数字和实体。

因此，Claim-Evidence 后续的证据匹配和指标聚合可能建立在错误的 Claim 列表上。

## 2. 典型问题

### 2.1 Markdown 标题和列表项被误认为 Claim

以下内容不是事实断言，但可能因为长度满足条件而进入 Claim 列表：

```text
### 基本面分析
- **盈利能力**：
```

它们会被送入证据匹配，可能增加 `unsupported` 或 `weakly_supported` 数量。

### 2.2 换行把一个事实拆成多个片段

例如原始内容可能被拆成：

```text
贵州茅台（股票代码：600519
SH）是中国知名的高端白酒品牌
```

或者：

```text
2025 年每股收益（EPS）为 65
66 元，2024 年为 68 元
```

这会造成以下问题：

- 股票代码、日期、金额和单位不再完整；
- 结构化数字、实体和日期校验可能无法触发；
- 证据匹配可能选择错误的 evidence；
- 同一事实可能被错误拆成多个 Claim。

### 2.3 前 20 条限制造成截断

`[:20]` 的作用是限制计算量、数据库大小和前端展示规模，但它只是数量上限，不能
保证前 20 条都是事实 Claim。

长报告前部通常包含标题、目录、字段名和格式片段。如果这些内容占满前 20 条，后续
真正重要的财务数字、风险结论或投资判断就会被静默丢弃。

可能被影响的指标包括：

- `evidence_coverage`
- `unsupported_ratio`
- `weakly_supported_ratio`
- Claim 级幻觉预测
- 人工复核列表中的 Claim 数量和优先级

## 3. 设计目标

优化后应满足以下目标：

1. Claim 应是相对完整、可独立验证的事实或结论句。
2. Markdown 标题、纯格式行和字段标签不应默认进入 Claim 评分分母。
3. 股票代码、数字、单位、日期、百分比和括号内容不应因普通换行而损坏。
4. 数量上限应在清洗和候选筛选之后应用，而不是直接截断原始分割结果。
5. 对被排除、被截断或无法判断的内容保留原因和统计信息，避免静默丢失。
6. 保持现有 `ClaimEvidence`、`ScoreResult.claims` 和 Claim-Evidence 映射接口兼容。

## 4. 优化方案

### 4.1 输入归一化

- 统一 CRLF、Unicode 空白和连续空白。
- 识别常见异常断行，不在金额、百分号、日期、股票代码、括号和英文缩写内部直接切分。
- 对 PDF/OCR 风格的断行进行有限合并，例如：

```text
65\n66 元       -> 65.66 元或保留为待确认片段
600519\nSH     -> 600519 SH
```

- 保留清洗前后的文本位置或映射关系，方便人工复核回看原文。

异常合并不能无条件执行。无法确定两个数字应当合并时，应保留原始片段并降低
Claim 候选优先级，而不是擅自改变事实内容。

### 4.2 Markdown 结构识别

对以下结构进行识别和分类：

- `#`、`##`、`###` 等标题；
- 只有字段名或格式标记的列表项；
- Markdown 表格表头和分隔线；
- 引用块、代码块和水平分隔线；
- 包含完整事实的普通列表项。

标题、表格分隔线和纯格式行应排除。完整列表项仍应作为候选 Claim，例如：

```text
- 2025 年净利润为 823 亿元。
```

应保留为：

```text
2025 年净利润为 823 亿元。
```

### 4.3 分离候选片段与事实 Claim

建议把抽取过程拆成以下阶段：

```text
原始输出
  -> 文本/Markdown 归一化
  -> 候选片段生成
  -> 片段合并和完整性检查
  -> 标题/格式/残缺片段过滤
  -> Claim 候选排序
  -> 应用数量上限
  -> ClaimEvidence 构造
```

可以使用以下信号提高候选质量：

- 包含数字、日期、股票代码、金额或百分比；
- 包含完整主语和谓语；
- 包含“是、为、达到、上涨、下降、同比、位于、来自”等事实或比较谓词；
- 具有完整句末标点，或是语义完整的列表项。

不满足条件的标题、字段标签和残缺片段不应直接创建 Claim。可以记录为排除项，附带
`excluded_reason`，但不进入证据覆盖率和幻觉指标的分母。

### 4.4 重新定义数量上限

保留单 trial 最多 20 条 Claim 的默认限制，但应在候选清洗和排序之后执行。

建议额外记录：

```text
claim_candidate_count
claim_count
claim_truncated
claim_truncated_count
claim_truncated_at
```

如果报告很长，优先考虑按段落或章节分批评分，而不是简单丢弃第 21 条之后的内容。

## 5. 预期结果

对于类似以下输入：

```text
### 基本面分析
- **盈利能力**：
- 2025 年每股收益（EPS）为 65.66 元，2024 年为 68 元。
- 2025 年净利润为 823 亿元。
```

理想的 Claim 列表应类似：

```text
2025 年每股收益（EPS）为 65.66 元，2024 年为 68 元。
2025 年净利润为 823 亿元。
```

而不应包含：

```text
### 基本面分析
- **盈利能力**：
2025 年每股收益（EPS）为 65
66 元，2024 年为 68 元
```

## 6. 测试计划

新增 Claim 抽取回归测试，至少覆盖：

- 中文、英文和混合标点；
- Markdown 标题、列表、表格和代码块；
- 多段落和长报告；
- 跨行股票代码、日期、金额、单位、百分比和括号；
- 被拆开的中英文缩写，例如 `EPS`、`SH`；
- 前 20 条中包含大量标题时，后续事实 Claim 不被静默丢弃；
- 超过数量上限时正确生成截断统计；
- 排除项不进入 `evidence_coverage`、`unsupported_ratio` 和幻觉指标分母。

## 7. 验收指标

在固定回归集和人工标注集上分别报告：

- Claim 抽取准确率；
- 标题/格式碎片误收率；
- Claim 截断率；
- 异常换行影响比例；
- 数字、实体、日期归一化后的保持率；
- Claim-Evidence verdict 与人工标注的一致率；
- 按 `structured_numeric_check`、`structured_entity_check`、`lexical_only` 分层的准确率。

在这些指标达到预设阈值前，`evidence_quality` 的 Claim 级结果只能作为粗筛和人工复核
输入，不能直接解释为事实准确率或幻觉检测准确率。

## 8. 结构化决策链与决策审计优化（2026-09-11 记录）

> 关联案例：`vibetask_0308018767424b9a926a2f6be3dfe6ba`
>
> 相关实现：`app/services/explainability/audit_service.py`、
> `app/routers/decision_audit.py`、`frontend/src/views/Evaluation/DecisionAudit.vue`、
> `frontend/src/views/VibeAgent/workbench.ts`

### 8.1 结构化决策链应展示什么

结构化决策链不是运行事件的简单时间列表，而是可以追溯“输入如何变成结论”的审计结构。
一条完整链路至少应能关联以下节点：

```text
用户输入/任务目标
  -> 检索信息或调用工具
  -> 获取证据
  -> 分析候选方案
  -> 形成结构化决策
  -> 输出结论
  -> 校验或人工复核（如有）
```

数据层应保留节点之间的任务、会话、序号和证据关联，至少覆盖：

- `decision_records`：结构化决策节点及其决策内容；
- `eval_trace_events`：检索、证据、引用和其他评测 trace；
- `vibe_agent_events`：运行期间产生的事件；
- `explanations`：决策解释；
- `validations`：决策校验；
- `reviews`：人工复核结果；
- 最终输出及其对应的 task/session。

页面需要能回答：做出了什么决策、依据了哪些证据、经过了哪些步骤、最终输出是什么、
是否经过校验或人工复核，而不是只显示“有无结构化决策链”。

### 8.2 当前案例的问题与 Bug 判定

查询 `vibetask_0308018767424b9a926a2f6be3dfe6ba` 时，页面提示没有结构化决策链，但当前
审计服务仍会查询运行事件、trace、操作日志、解释、校验和复核数据。

需要区分以下三种状态：

1. 没有任何审计数据：确实无法找到该标识对应的任务或会话；
2. 存在运行事件、trace 或日志，但没有 `decision_records`：运行过程存在，结构化决策链缺失；
3. 存在 `decision_records`：可以展示完整或部分结构化决策链。

因此，本案例不能仅用“没有 `decision_records`”解释为“没有决策过程”。如果该对话确实有
运行事件但没有结构化决策记录，这是数据链路缺陷；如果 `decision_records` 已存在但因
关联字段不一致而没有查到，则是审计查询 Bug；即使数据确实未生成，页面把有运行数据的
记录直接归类为“没有结构化决策链”也属于降级展示缺陷。

排查和回归测试必须核对以下关联：

- `vibe_agent_tasks.task_id` 与输入标识是否一致；
- 任务对应的 `session_id`；
- `vibe_agent_events.task_id/session_id`；
- `decision_records.task_id/session_id`；
- `eval_trace_events` 的 `task_id/session_id/trial_id/business_id`；
- 查询使用的 `scope=task` 或 `scope=session` 是否与数据实际归属一致。

### 8.3 审计链状态和降级展示

后端应返回可区分的审计状态及各类数据数量，不以单一布尔值表示结果：

```text
complete              存在结构化决策记录及其关联审计数据
partial                存在结构化决策记录，但关联数据不完整
events_without_chain   有运行事件/trace/日志，但没有结构化决策记录
empty                  没有找到任何相关审计数据
```

当状态为 `events_without_chain` 时，页面应明确显示：

> 本次对话存在运行事件，但尚未生成结构化决策链。以下内容为原始运行事件。

同时展示 task ID、session ID、运行事件数、trace 数、结构化决策记录数和查询范围，帮助定位
是决策记录未落库还是任务、会话关联错误。原始运行事件可以作为降级审计视图，但不能伪装
成完整的结构化决策链，也不能据此声称已经具备完整的决策可追溯性。

### 8.4 运行事件分页

当前审计服务将运行事件一次性查询并限制为最多 1000 条，前端也没有独立的分页状态。
应为运行事件提供后端分页接口，避免大任务一次性加载全部事件并突破固定上限：

```text
GET /api/decision-audit/chains/{identifier}/events
参数：scope、page、page_size
```

返回至少包含：

```json
{
  "items": [],
  "page": 1,
  "page_size": 20,
  "total": 86,
  "has_more": true
}
```

分页排序应保持事件序号或创建时间的稳定顺序，并沿用现有权限校验和 task/session 查询范围。
分页只解决事件查看问题，不能替代结构化决策记录的生成和关联修复。

### 8.5 运行事件中文名称

运行事件列表只需要显示中文事件名称，不额外增加事件含义说明。名称映射必须同时考虑
`event_type` 和 payload 中的 `phase`，因为工具返回有可能使用 `event_type=tool_call`、
`payload.phase=tool_result` 表示，而不是单独的 `tool_result` 事件类型。

建议至少覆盖：

| 原始事件 | 中文名称 |
| --- | --- |
| `task_created` | 创建任务 |
| `task_status` | 任务状态变更 |
| `tool_call` | 调用工具 |
| `tool_result` 或 `tool_call + phase=tool_result` | 工具返回 |
| `decision` | 形成决策 |
| `evidence` | 获取证据 |
| `retrieval` | 检索信息 |
| `citation` | 添加引用 |
| `message` | 生成消息 |
| `error` | 执行异常 |

未知事件保留原始名称，避免因映射缺失而丢失审计信息。

### 8.6 验收标准

- 对上述案例能明确判断是结构化决策记录未生成、关联错误、查询范围错误，还是确实无审计数据；
- 具备结构化决策记录时，页面能按节点展示决策、证据、解释、校验、输出和复核关联；
- 只有运行事件时，页面显示“存在运行事件但尚未生成结构化决策链”，并展示原始事件；
- 运行事件通过后端分页加载，分页结果有稳定顺序、总数和权限校验；
- 运行事件在列表中显示中文名称，工具返回事件能正确识别 payload phase；
- 不将原始运行事件冒充为完整结构化决策链；
- 增加针对 task/session/decision record 关联、空数据、部分数据和分页边界的回归测试。

## 9. 线上 Bad Case 自动发现配置管理（2026-09-11 记录）

> 相关实现：`app/services/eval/online_badcase_service.py`、
> `app/core/config.py`、自进化管理模块

### 8.1 问题概述

当前线上 Bad Case 自动发现依赖环境变量配置，主要包括：

- `ONLINE_BADCASE_ENABLED`
- `ONLINE_BADCASE_ENABLE_JUDGE`
- `ONLINE_BADCASE_SOFT_SAMPLE_RATE`
- `ONLINE_BADCASE_CONFIDENCE_THRESHOLD`
- `ONLINE_BADCASE_JUDGE_THRESHOLD`
- `ONLINE_BADCASE_EVIDENCE_THRESHOLD`
- `ONLINE_BADCASE_MAX_CONTENT_LENGTH`

这种方式存在以下问题：

1. 需要修改部署环境或容器配置，运营和评测人员无法在系统内管理；
2. 配置修改依赖重启服务，不能明确表达何时生效；
3. 当前值、修改人、修改时间和修改原因缺少统一展示和审计；
4. 线上自动发现属于自进化闭环的一部分，但配置入口与 Bad Case、复核、回流流程分散；
5. 环境变量适合部署级默认值，不适合频繁调整的采样率、阈值和自动确认策略。

### 8.2 目标

在“自进化”模块中增加线上 Bad Case 自动发现管理页，将上述字段改为系统级可管理配置，
使授权用户能够：

- 查看当前生效配置、部署默认值和配置来源；
- 开关线上 Bad Case 自动发现；
- 开关线上 LLM Judge 软信号；
- 调整软信号采样率、自动确认置信度和各评分阈值；
- 配置内容截断上限，并看到字段范围和风险提示；
- 保存、校验、回滚和查看配置变更历史。

### 8.3 方案

配置采用“环境变量作为初始默认值，数据库配置作为运行时覆盖”的分层方式：

```text
环境变量默认值
  -> 系统配置初始化/迁移
  -> 自进化配置集合中的当前版本
  -> 线上 Bad Case Collector 运行时读取
```

不再要求业务人员直接修改环境变量。环境变量仍保留为首次部署和数据库不可用时的安全
默认值，但一旦系统配置已初始化，应以数据库中的已发布配置为准。

建议新增独立的线上 Bad Case 配置记录，至少包含：

```text
config_key
version
enabled
enable_judge
soft_sample_rate
confidence_threshold
judge_threshold
evidence_threshold
max_content_length
status              # draft / published / archived
updated_by
updated_at
change_reason
```

字段校验规则应与现有 `Settings` 约束一致：

- `soft_sample_rate`、各置信度和评分阈值范围为 `0~1`；
- `max_content_length` 应限制在合理范围内，避免线上事件过大；
- 开启 `enable_judge` 时，应提示检查 `EVAL_JUDGE_MODEL` 和模型凭据；
- 禁止发布不完整或无法解析的配置；
- 关闭总开关时不运行线上自动发现，但不删除已有 Bad Case 和指标记录。

运行时不应继续在 `online_badcase_service.py` 中直接散落读取多个 `settings.*` 字段，
而应通过统一的配置服务获取一份已校验的快照，例如：

```text
OnlineBadcaseConfigService.get_effective_config()
  -> OnlineBadcaseCollector / collect_soft_signals / adjudicate
```

为避免每次线上事件查询数据库，配置服务可以使用进程内短 TTL 缓存或发布后主动失效缓存。
配置读取失败时必须 fail-closed：使用最近一次已发布的有效配置；如果没有有效配置，则回退到
安全默认值并关闭线上自动发现，不能默认开启。

### 8.4 管理页范围

自进化管理页建议分为三部分：

1. **当前配置**：展示开关、采样率、阈值、当前版本、生效时间和配置来源；
2. **编辑和发布**：表单校验、风险提示、变更原因、发布确认；
3. **历史与回滚**：按版本查看变更前后差异、修改人和发布时间，并支持回滚到最近有效版本。

页面应明确区分以下状态：

- 配置已保存但未发布；
- 配置已发布并已被运行时读取；
- 配置发布成功但缓存尚未刷新；
- 配置依赖缺失，例如 Judge 模型未配置；
- 线上自动发现已关闭，但历史 Bad Case 仍可查看和回流。

### 8.5 权限、审计与生效策略

- 只允许具备自进化配置管理权限的用户修改和发布；
- 普通复核人员只读查看，不应改变线上采样和自动确认策略；
- 每次发布记录操作者、时间、变更原因、版本差异和生效结果；
- 配置发布默认即时生效，不要求重启服务；
- 配置变更不影响已经创建的 Bad Case，只影响后续线上终态事件；
- 关闭配置时仍保留指标采集和历史查询能力，但不得新建线上 Bad Case。

### 8.6 实施顺序

```text
配置模型与数据库持久化
  -> 默认值迁移与统一读取服务
  -> 自进化配置管理 API
  -> 自进化管理页
  -> Collector/软评分器接入运行时配置
  -> 权限、审计、缓存失效和回滚
  -> 配置迁移、关闭开关、边界值和并发发布测试
```

本需求只改变配置管理方式，不改变当前硬失败、软信号、人工复核和 Bad Case 去重规则。
“自动发现并入 Bad Case 池”与“人工复核后回流评测集”的流程边界也应保持不变。

---

## 9. LLM Judge 与当前默认模型不一致（2026-09-11 记录）

> 相关实现：`app/services/eval/scorers/llm_judge_scorer.py`、
> `app/services/eval/online_badcase_service.py`、`app/services/eval/scorer_hub.py`、
> `app/services/eval/runner_service.py`、`app/routers/eval.py`、`app/models/eval.py`

### 8.1 问题概述

生产环境默认 LLM 已统一为 DeepSeek，但 `LLMJudgeScorer` 仍以 `qwen-plus` 作为
默认 judge 模型，并强依赖 `dashscope` SDK。这导致：

- 未安装 `dashscope` 或未配置阿里云凭据的环境中，`is_available` 返回 False；
- 打分器直接返回 `ScoreStatus.NOT_CONFIGURED`，不会调用任何模型；
- 所有依赖 LLM Judge 的评测维度（综合分、金融 rubric 打分、事实性评审）会静默
  失效，前端只显示 “LLM Judge 不可用/未配置”。

### 8.2 涉及位置与现状

| 位置 | 现状 |
| --- | --- |
| `llm_judge_scorer.py:140` | `judge_model: str = "qwen-plus"`，硬编码默认值 |
| `llm_judge_scorer.py:162-169` | `is_available` 通过 `import dashscope` 判断可用性 |
| `llm_judge_scorer.py:_call_judge` | 走 dashscope SDK 调用，无法复用系统统一 LLM 适配器 |
| `online_badcase_service.py:248` | `LLMJudgeScorer(judge_model=settings.EVAL_JUDGE_MODEL)`，但仍走 dashscope |
| `scorer_hub.py:261` | `judge_model=run_config.get("judge_model") or "qwen-plus"`，fallback 依旧是 qwen-plus |
| `runner_service.py:216` | 从 `run_config.judge_model` 传参，未做模型可用性回退 |
| `app/routers/eval.py:88`、`app/models/eval.py:290` | `judge_model` 字段默认值为空，未校验模型是否在受支持列表内 |

配置项方面：`settings.EVAL_JUDGE_MODEL` 目前也倾向指向阿里云模型；没有集中的
“默认 judge 模型来源单一事实源”。

### 8.3 影响面

- **综合评分失真**：LLM Judge 是六个评分器中唯一能覆盖专业性、逻辑连贯性、结论
  合理性等主观维度的打分器。它失效后，`ScoreSummary` 中的 LLM 维度会缺失或降级，
  综合分被 rule-based 打分器主导。
- **case 复盘信号不足**：Bad case、Online Bad case 复盘链路重度依赖 LLM Judge
  输出的 `overall_reason` 与 `raw_response`。当前会直接标记为 `NOT_CONFIGURED`，
  复盘看板显示为空。
- **回归对比不一致**：跨环境（本地 vs. 线上）跑同一 case，只要 dashscope 环境
  差异，就会得到完全不同的 `passed` 结果，破坏可复现性。

### 8.4 优化方案

优化目标：**Judge 模型来源、调用通道与系统统一 LLM 配置对齐，不再硬编码单一供应商。**

1. **抽象 Judge 调用通道**
   - 将 `_call_judge` 从 dashscope 迁移到统一的 LLM 适配层（DeepSeek adapter、
     Qwen adapter、OpenAI-compatible adapter 等）。
   - `LLMJudgeScorer.__init__` 允许注入 adapter，测试时可注入 mock。
2. **可用性判断改造**
   - `is_available` 不再检测 `dashscope`，改为检测：
     - 是否存在受支持的 adapter；
     - 该 adapter 对应的凭据（如 `DEEPSEEK_API_KEY`）是否已配置；
     - `settings.EVAL_JUDGE_MODEL` 是否落在受支持模型集合内。
3. **默认模型策略**
   - 引入 `settings.EVAL_JUDGE_MODEL_DEFAULT`（或复用现有 `DEFAULT_LLM_MODEL`）
     作为唯一默认来源，取值示例：`deepseek-chat`、`deepseek-reasoner`。
   - `scorer_hub.py` 和 `LLMJudgeScorer` 默认值必须来自同一常量，避免代码多处
     写死 `qwen-plus`。
4. **run_config 校验**
   - `RunConfig.judge_model` 通过 API 提交时，服务端校验该模型是否可用；不可
     用时给出明确 4xx 而不是静默 fallback。
5. **降级策略**
   - 当 judge 模型临时不可用时，返回 `ScoreStatus.NOT_CONFIGURED` 之前，允许
     配置一个次选模型（例如 DeepSeek 主用 + Qwen 备用），减少大规模评测中断。
6. **可观测性**
   - 在 `raw_output` 中记录实际使用的 `judge_model`、adapter 名称与调用耗时；
   - runner_service 汇总每次 run 中 LLM Judge 的成功率与失败原因，便于运维。

### 8.5 迁移步骤建议

1. 在 `app/services/eval/scorers/llm_judge_scorer.py` 中新增 `_resolve_default_judge_model()`，从统一配置读取默认模型；
2. 抽象 `JudgeLLMClient` 接口，将 dashscope 调用封装为一个 adapter 实现；
3. 添加 DeepSeek adapter 实现，复用现有 LLM 客户端；
4. 修改 `is_available`、`_call_judge` 使用 adapter；
5. 更新 `online_badcase_service.py`、`scorer_hub.py`、`runner_service.py` 里的
   fallback 逻辑；
6. 更新 `app/routers/eval.py`、`app/models/eval.py` 中的字段校验和默认值；
7. 增加回归测试：
   - DeepSeek 环境下 `is_available` 为 True；
   - 未配置任何 judge 模型时返回 `NOT_CONFIGURED` 并记录明确原因；
   - `run_config.judge_model` 指定未支持模型时 API 层直接报错；
   - `raw_output.judge_model` 与实际调用模型一致。

### 8.6 与 Claim 抽取优化的关系

Claim 抽取（1–7 节）解决“送进 Judge 的输入是否干净”，本节解决“Judge 本身是否
真的在跑”。两者必须同步治理，否则：

- 只治 Claim 抽取：Judge 依然静默失效，事实性维度评分永远为 0；
- 只治 Judge 模型：Judge 会对错误切分的 Claim 打出错误分数，掩盖抽取问题。

建议在同一次评测平台迭代中一并推进。

---

## 9. 运行初始化失败：snapshot 与执行器契约断裂（2026-09-11 记录）

> 关联运行：`run_e6f260e9419a`
>
> 数据集：`ds_e2f3ca922896`，版本 `1.0.21`
>
> 相关实现：`app/services/eval/runner_service.py`、
> `app/models/eval.py`、`frontend/src/views/Evaluation/RunDetail.vue`

### 9.1 现象与日志证据

本次运行在页面上显示：

```text
63 个 Case
0/63 完成，0 失败
Trial 列表：0 条
```

后端日志显示运行创建和启动接口均返回成功，但后台任务随后立即失败：

```text
Created eval run run_e6f260e9419a for dataset ds_e2f3ca922896 v1.0.21 with snapshot
Started eval run run_e6f260e9419a
Eval run run_e6f260e9419a failed: 'case_id'
```

因此这不是 63 个 Trial 全部失败，而是**一个 Trial 都没有创建出来**。失败发生在
执行器初始化 Case 的阶段，早于 Agent runtime、scorer、Claim 抽取和幻觉指标计算。

### 9.2 根因：运行快照丢失 `case_id`

`create_run()` 在构造 `snapshot.case_contents` 时使用 `case_id` 作为字典 key，但没有
将它写入 value：

```python
case_contents[c["case_id"]] = {
    "name": c.get("name", ""),
    "input": c.get("input", {}),
    "expected_output": c.get("expected_output"),
    "scoring_criteria": c.get("scoring_criteria", {}),
    # 没有 "case_id": c["case_id"]
}
```

`_resolve_run_cases()` 随后只返回 `case_contents.values()`。执行阶段的
`_execute_run()` 却假设每个 Case 都有 `case["case_id"]`，于是触发：

```text
KeyError: 'case_id'
```

实际链路是：

```text
dataset case
  -> create_run()
  -> snapshot.case_contents
  -> _resolve_run_cases()
  -> _execute_run()
  -> case["case_id"] 失败
  -> 0 个 Trial
```

这是 `snapshot -> executor` 的数据契约不一致，不是幻觉检测指标实现本身的问题。

### 9.3 为什么现有测试没有发现

现有 `test_runner_resolves_cases_from_snapshot` 的 fixture 手工构造了如下快照：

```python
"case_contents": {
    "case_1": {
        "case_id": "case_1",
        "input": {"prompt": "locked"},
    }
}
```

测试数据本身已经满足执行器要求，但没有覆盖真实的完整链路：

```text
真实 dataset case
  -> create_run 持久化快照
  -> start_run
  -> _resolve_run_cases
  -> 创建第一个 Trial
```

因此当前测试验证了“合法快照可以被读取”，没有验证“创建出来的快照一定合法”。
这也是 OpenSpec `add-hallucination-detection-metrics` 中完整链路验证任务仍未完成的
具体例子。

### 9.4 暴露出的评测平台问题

#### P0：创建成功不代表运行可执行

`POST /api/eval/runs` 只验证了数据集和 Case 数量，没有验证生成的快照能否被执行器
消费。运行可以以 HTTP 200 创建成功，但启动后立即失败。

#### P0：启动接口是异步 fire-and-forget

`start_run()` 将 `_execute_run()` 放入后台 task 后立即返回成功。后台 task 的异常只能
稍后写入 `eval_runs.error_message`，调用方无法在启动请求中感知初始化失败。

#### P0：Run 级失败和 Trial 级失败没有清晰区分

当前页面将“运行初始化失败”和“每个 Trial 执行失败”都通过进度区域表达。结果是：

```text
0/63 完成，0 失败，0 Trial
```

看起来像运行尚未开始，而不是运行已经失败。

#### P1：运行详情没有展示失败原因

后端已保存 `error_message`，但运行详情页没有在状态卡片中显式展示。用户只能看到
“失败”和空的 Trial 表格，无法判断是快照错误、配置错误、Agent 错误还是数据库错误。

#### P1：缺少运行前 preflight

以下契约目前主要依赖执行过程中才暴露：

- `total_cases` 与 snapshot 中 Case 数量一致；
- 每个 Case 都有稳定的 `case_id`；
- `input.prompt` 存在且类型正确；
- `snapshot.case_contents` 可被重新解析；
- `timeout_seconds`、scorer 和 judge 配置可用；
- 数据集版本和 Case 快照版本一致。

#### P1：部分失败状态缺少结构化错误分类

现在主要保存一段 `error_message` 字符串，后续无法稳定区分：

```text
run_initialization_error
case_validation_error
runtime_error
timeout
scorer_error
storage_error
```

这会影响失败聚类、告警、重试策略和评测质量统计。

### 9.5 优化方案

#### 方案一：修复并固化 snapshot 数据契约

`case_contents` 的 key 和 value 都保留 `case_id`，不要依赖字典 key 传递业务字段：

```python
case_contents[c["case_id"]] = {
    "case_id": c["case_id"],
    "name": c.get("name", ""),
    "input": c.get("input", {}),
    "expected_output": c.get("expected_output"),
    "scoring_criteria": c.get("scoring_criteria", {}),
    "skill_eval": c.get("skill_eval")
    or (c.get("scoring_criteria") or {}).get("skill_eval"),
    "tags": c.get("tags", []),
    "difficulty": c.get("difficulty", "medium"),
    "category": c.get("category", "general"),
}
```

同时应在 `_resolve_run_cases()` 返回前做统一归一化，兼容历史快照：

```text
snapshot value 已有 case_id -> 直接使用
snapshot value 缺少 case_id、但 dict key 可用 -> 从 key 补回
两者都缺失 -> 明确抛出 CaseSnapshotValidationError
```

这样既修复新运行，也避免历史数据因为快照格式差异而产生不透明的 `KeyError`。

#### 方案二：增加 preflight 阶段

在 `start_run()` 创建后台 task 之前，或 `_execute_run()` 创建 Trial 之前，增加显式
的运行前检查：

```text
加载 Run snapshot
  -> 校验 Case 数量
  -> 校验 case_id 唯一且非空
  -> 校验 input.prompt
  -> 校验 snapshot_version / dataset_version
  -> 校验 scorer/judge 配置
  -> 通过后才创建 Trial
```

preflight 结果应结构化保存：

```json
{
  "status": "passed",
  "checked_cases": 63,
  "errors": [],
  "warnings": []
}
```

失败时应返回明确的 `run_initialization_error`，而不是让执行器在任意字段访问处抛出
原始 Python 异常。

#### 方案三：补齐端到端运行测试

至少增加以下测试：

1. 从标准 dataset case 调用 `create_run()`，检查持久化 snapshot 中每个 value 都有
   `case_id`。
2. 从该 snapshot 调用 `_resolve_run_cases()`，检查返回 Case 可直接被执行器消费。
3. 启动一个至少包含 1 个 Case、1 个 Trial 的完整运行，确认会创建 Trial。
4. snapshot 缺少 `case_id` 时，验证返回结构化初始化错误，而不是裸 `KeyError`。
5. 验证历史快照兼容：`case_id` 只存在于 map key 时可以补回。
6. 验证 63 Case 的真实固定数据集不会出现 `total_cases=63` 但 Trial 为 0 的情况。
7. 验证运行初始化失败时，Run 的 `completed_trials` 和 `failed_trials` 不被误填为
   运行级 Trial 结果。

测试重点应从 scorer 单元测试扩展到：

```text
dataset -> run snapshot -> preflight -> trial -> runtime -> scorer -> metrics -> API
```

#### 方案四：改进 Run/Trial 状态模型

建议将运行状态和失败阶段分开记录：

```text
Run status:
pending -> preflighting -> running -> completed / failed / cancelled

Failure stage:
none
snapshot_validation
case_validation
runtime
scoring
aggregation
storage
```

运行初始化失败时：

- Run 状态为 `failed`；
- `failure_stage` 为 `snapshot_validation` 或 `case_validation`；
- `error_code` 为稳定枚举；
- `error_message` 保存可读详情；
- `completed_trials=0`、`failed_trials=0`；
- `trial_count=0` 明确表示没有进入 Trial 阶段。

这样可以区分：

```text
Run failed before Trial creation
Run completed with N failed Trials
Run cancelled while Trials were running
```

#### 方案五：改进前端运行详情

运行详情页应将 Run 级失败原因放在状态摘要的首屏：

```text
运行状态：失败
失败阶段：快照校验
错误代码：CASE_SNAPSHOT_MISSING_FIELD
错误原因：snapshot case_contents[case_x] 缺少 case_id
Trial：未创建
```

同时将进度展示拆成：

- Case 总数：63；
- Trial 计划数：63；
- Trial 已创建数：0；
- Trial 已完成数：0；
- Trial 执行失败数：0；
- Run 初始化状态：失败。

不要把“未创建 Trial”显示成“0 个失败”，否则会掩盖运行器自身的故障。

#### 方案六：建立失败归因与重试边界

不同失败阶段应有不同处理方式：

| 失败阶段 | 是否自动重试 | 处理方式 |
| --- | --- | --- |
| snapshot 校验 | 否 | 修复数据契约后创建新 Run |
| Case 校验 | 否 | 修复数据集或明确跳过非法 Case |
| runtime 临时错误 | 可配置 | 按 Trial 重试并保留每次尝试 |
| timeout | 可配置 | 按 Trial 重试并记录超时原因 |
| scorer 错误 | 通常否 | 标记 score 为 error，不重跑 Agent |
| metrics 聚合错误 | 否 | 保留 Trial 结果，允许单独重算指标 |

运行级失败不能简单重试整个 Agent 链路。应先判断失败发生在哪个阶段，避免重复消耗
模型调用成本。

### 9.6 优先级与验收标准

建议按以下顺序推进：

#### P0：先恢复可运行性

- 补齐 snapshot value 中的 `case_id`；
- 对 `_resolve_run_cases()` 增加历史快照兼容；
- 增加 1 Case 的端到端启动测试；
- 确认真实 63 Case 数据集至少能创建第一个 Trial。

#### P1：让失败可定位

- 增加 preflight；
- 统一 `error_code`、`failure_stage`；
- API 返回并持久化结构化初始化结果；
- 前端首屏展示 Run 级失败原因和 Trial 创建状态。

#### P2：让评测结果可运营

- 按失败阶段和错误代码聚类；
- 建立初始化失败、Trial 失败、评分失败、聚合失败四类趋势；
- 为可重试阶段设计限次重试和成本统计；
- 将完整链路纳入固定回归集和 Release Gate。

验收时至少满足：

```text
合法 snapshot -> preflight passed -> Trial successfully created
非法 snapshot -> preflight failed -> no Trial created -> clear error shown
Trial runtime failure -> Trial failed with reason -> Run remains aggregatable
Scorer failure -> score error/not_configured -> Agent output remains inspectable
```

### 9.7 与 Claim 抽取和幻觉指标的关系

这次故障发生在 Claim 抽取之前，但它直接影响后续所有评测指标：

```text
运行初始化失败
  -> 没有 Trial
  -> 没有 Agent output
  -> 没有 trace/evidence
  -> 没有 Claim
  -> 没有 scorer prediction
  -> 没有 Recall/Precision/F1
```

因此，Claim 级幻觉评测不能只验证 `EvidenceQualityScorer` 和
`MetricsService.compute_hallucination_metrics()`。必须同时验证从数据集快照到指标展示的
完整路径，否则“指标没有结果”无法区分是没有真值、没有 Claim、scorer 未配置，还是
运行根本没有进入 Trial 阶段。

## 10. 发布后质量观测页面（2026-09-11 记录）

> 状态：需求讨论完成，尚未实现
>
> 范围：Agent 自进化发布后的质量观测与后续动作查看
>
> 结论：新增独立前端页面，第一版只做人工提交观测和只读查看后续动作

### 10.1 问题

当前发布后质量观测只有后端接口，没有前端页面。管理员要完成发布后观测，只能手动调用：

- `POST /api/evolution/post-release/observe`
- `GET /api/evolution/follow-up-actions`

这不是管理员可以日常使用的形态。用户需要坐在页面上完成：

1. 选择一条已发布的回执；
2. 填写或回填发布后质量指标；
3. 查看观测结论和是否建议回滚；
4. 查看系统生成的后续动作。

### 10.2 现状

后端已经具备最小闭环能力：

- `receipt_service` 保存 `evolution_receipts` 发布回执；
- `governance_service.evaluate_post_release()` 根据指标判断发布后质量是否退化；
- `governance_service.route_post_release_observation()` 生成 `evolution_follow_up_actions`；
- `GET /api/evolution/follow-up-actions` 可以列出后续动作。

当前自动判定阈值：

- `success_rate >= 0.8`
- `safety avg_score >= 0.8`
- `evidence_quality avg_score >= 0.6`
- `latency mean_ms <= 30000`
- `cost total_usd <= 5.0`

不达标时系统建议回滚或生成 Bad Case 后续动作；同一 artifact 在观察窗口内连续升级，
第 3 次会生成 stop 候选。

### 10.3 已确认的需求

1. 发布后观测必须放在“自进化”模块下，作为独立页面。
2. 页面不合并进“进化回执”或“Artifact 管理”。
3. 第一版先做人工提交观测指标，不做自动拉取线上指标。
4. 第一版先做后续动作只读展示，不在页面上直接执行回滚或 stop。
5. 回滚仍沿用现有“Artifact 管理”页面能力。

### 10.4 推荐 MVP 方案

新增独立页面，建议菜单名“发布后观测”，路由可定为：

```text
/evolution/observation
```

页面分为两个区域：

#### 10.4.1 发布后观测提交区

- 从已发布回执列表中选择一条 `receipt_id`；
- 填写观测指标：
  - `success_rate`
  - `safety`
  - `evidence_quality`
  - `latency mean_ms`
  - `cost total_usd`
- 点击“提交观测”；
- 提交后展示：
  - 是否通过；
  - 哪些检查失败；
  - 是否建议回滚；
  - 本次生成的后续动作。

#### 10.4.2 后续动作列表

- 展示 `GET /api/evolution/follow-up-actions` 的结果；
- 字段包括：
  - `action_id`
  - `action_type`：rollback / bad_case / stop
  - `severity`
  - `escalation_level`
  - `status`
  - `artifact_id`
  - `receipt_id`
  - `proposal_id`
  - `created_at`
  - 详情或原始 JSON
- `pending` 动作高亮；
- 关联提案和回执可以跳转到现有详情页。

### 10.5 实施范围

第一版为纯前端改动，后端接口保持不变：

- `frontend/src/api/evolutionClient.ts` 增加 `observePostRelease()`；
- 新增 `frontend/src/views/Evolution/PostReleaseObservation.vue`；
- `frontend/src/router/index.ts` 增加独立路由；
- `frontend/src/components/Layout/SidebarMenu.vue` 增加菜单项；
- `frontend/src/utils/sidebarEntries.ts` 同步补充入口清单。

### 10.6 暂不实现

- 从评测 run 或线上运行自动回填指标；
- 页面直接执行 rollback / stop；
- 后续动作的“处理”状态更新；
- 发布后阈值在页面上可配置。

这些内容等页面投入使用、确认指标来源后，再作为第二阶段需求补上。

### 10.7 验收标准

1. 管理员可以在“自进化”下看到并访问独立“发布后观测”页面。
2. 页面可以加载回执列表和后续动作列表。
3. 选择回执并提交指标后，页面展示观测结论。
4. 提交后刷新后续动作列表，能看到本次生成的 rollback / bad_case / stop 候选。
5. 不修改后端接口，不影响现有提案、回执和 Artifact 页面。
